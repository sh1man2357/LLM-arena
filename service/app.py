"""Local Bot import, single runs, shared recording/live frames and leaderboard."""
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import secrets
from typing import Literal
from urllib.parse import urlparse

from fastapi import FastAPI, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from runner.io import ROOT, sha_file
from runner.match import components
from service import APP_VERSION
from service.bots import (MAX_SOURCE_BYTES, active_bot_ids, edit_bot, import_bot, listed_bots,
                          manage_bots, prepare_baselines, public_bot, require_available_bots)
from service.jobs import BusyError, Executor
from service.history import filter_runs, manage_runs
from service.leaderboard import leaderboard
from service.replays import decode, project
from service.store import Store, utc_now


class APIError(Exception):
    def __init__(self, code, message, status=400):
        self.code, self.message, self.status = code, message, status


class MatchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bot_ids: list[str] = Field(min_length=2, max_length=8)
    map_seed: int | None = Field(default=None, ge=0, le=4294967295)
    game_id: Literal["bomberman", "gomoku"] = "bomberman"
    opening_mode: Literal["empty", "library"] = "empty"


class HumanMatchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bot_id: str = Field(min_length=1, max_length=100)
    human_slot: int = Field(default=0, ge=0, le=1, strict=True)


class HumanAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tick: int = Field(ge=0, le=225, strict=True)
    action: int = Field(ge=0, le=225, strict=True)


MatchStatus = Literal["pending", "running", "completed", "failed", "interrupted"]


class MatchTitle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=100)


class MatchManagement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["trash", "restore"]
    ids: list[str] = Field(default_factory=list, max_length=100)
    all_finished: bool = False
    q: str = Field(default="", max_length=100)
    status: MatchStatus | None = None
    game_id: Literal["bomberman", "gomoku"] | None = None


class BotEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(default="", max_length=100)
    description: str = Field(default="", max_length=1000)


class BotManagement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["trash", "restore"]
    ids: list[str] = Field(min_length=1, max_length=100)


def public_match(row):
    return dict(game_id=row.get("game_id", "bomberman"), **{k: row.get(k) for k in ("id", "title", "entrants", "status", "ticks", "result", "verified",
                                   "created", "finished", "map_seed", "diagnostic", "source_sha256", "opening_mode", "pair_id", "pair_index", "pair_runs",
                                   "mode", "human_slot", "waiting_tick")})


def create_app(data_root=None, *, demo=False, workers=False):
    store = Store(data_root or os.environ.get("ARENA_DATA", str(ROOT / "artifacts/local")))
    executor = Executor(store)

    @asynccontextmanager
    async def lifespan(app):
        if workers:
            executor.start()
        try:
            if demo:
                prepare_baselines(store, executor, "all")
            yield
        finally:
            if workers:
                executor.stop()

    app = FastAPI(title="LLM Arena core API", version=APP_VERSION, lifespan=lifespan)
    app.state.store, app.state.executor = store, executor

    @app.middleware("http")
    async def local_boundary(request, call_next):
        host = urlparse("http://" + request.headers.get("host", "")).hostname
        if host not in ("127.0.0.1", "localhost", "testserver"):
            return JSONResponse(dict(code="invalid_host", message="服务仅接受本机 Host。"), status_code=403)
        origin = request.headers.get("origin")
        if (origin and origin.rstrip("/") != str(request.base_url).rstrip("/")) or request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse(dict(code="invalid_origin", message="不接受外部来源请求。"), status_code=403)
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-arena-local") != "1":
            return JSONResponse(dict(code="local_intent_required", message="请从本机应用操作。"), status_code=403)
        length = request.headers.get("content-length")
        if length and (not length.isdigit() or int(length) > MAX_SOURCE_BYTES + 65536):
            return JSONResponse(dict(code="upload_too_large", message="请求超过大小限制。"), status_code=413)
        response = await call_next(request)
        response.headers.update({"X-Content-Type-Options": "nosniff", "Referrer-Policy": "same-origin",
                                 "Content-Security-Policy": "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'"})
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(APIError)
    async def api_error(request, exc):
        return JSONResponse(dict(code=exc.code, message=exc.message), status_code=exc.status)

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse(dict(code="not_found", message="没有找到该记录。"), status_code=404)

    @app.exception_handler(FileExistsError)
    async def conflict(request, exc):
        return JSONResponse(dict(code="conflict", message=str(exc)), status_code=409)

    @app.exception_handler(BusyError)
    async def busy(request, exc):
        return JSONResponse(dict(code="busy", message=str(exc)), status_code=409)

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse(dict(code="invalid_input", message=str(exc)), status_code=422)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, exc):
        return JSONResponse(dict(code="invalid_input", message="输入字段无效。"), status_code=422)

    @app.get("/health")
    def health():
        return dict(status="ready", app_version=APP_VERSION, ruleset="2", game_rulesets=dict(bomberman="2", gomoku="1"),
                    frontend_ready=(ROOT / "web/dist/index.html").exists())

    @app.get("/api/v1/status")
    def status():
        active = next((t for t in store.list("task") if t["status"] in ("pending", "running")), None)
        return dict(busy=active is not None, operation=active["kind"] if active else None)

    @app.get("/api/v1/bots")
    def bots(game_id: Literal["bomberman", "gomoku"] | None = None, trashed: bool = False):
        active = active_bot_ids(store.list("task"))
        return dict(items=[dict(public_bot(row), in_use=row["id"] in active) for row in listed_bots(store.list("bot"), trashed=trashed)
                           if not game_id or row.get("game_id", "bomberman") == game_id])

    @app.patch("/api/v1/bots/{identity}")
    def update_bot(identity: str, body: BotEdit):
        return public_bot(edit_bot(store, identity, body.model_dump(exclude_unset=True)))

    @app.post("/api/v1/bots/manage")
    def manage_bot_list(body: BotManagement):
        return manage_bots(store, body.action, body.ids)

    @app.post("/api/v1/bots", status_code=202)
    async def upload_bot(request: Request, file: UploadFile, name: str = Form(default=""),
                         game_id: Literal["bomberman", "gomoku"] = Form(default="bomberman")):
        if not (file.filename or "").lower().endswith(".cpp"):
            raise APIError("invalid_file", "请选择单文件 C++20 Bot（.cpp）。", 422)
        data = await file.read(MAX_SOURCE_BYTES + 1)
        if len(data) > MAX_SOURCE_BYTES:
            raise APIError("upload_too_large", "源码超过 1 MiB。", 413)
        try:
            row = import_bot(store, executor, data, name or Path(file.filename).stem,
                             request.headers.get("idempotency-key"), game_id)
        except UnicodeDecodeError:
            raise APIError("invalid_encoding", "源码须使用 UTF-8 编码。", 422)
        return public_bot(row)

    def frozen_bots(ids, game_id="bomberman"):
        result = []
        for identity in ids:  # Preserve the user's spawn order.
            bot = store.get("bot", identity)
            if bot.get("deleted_at"):
                raise FileExistsError("Bot 已在回收站，请先恢复后再开始对局。")
            if bot.get("game_id", "bomberman") != game_id:
                raise ValueError("Bot 所属游戏与对局不一致。")
            if bot["status"] != "ready" or not bot.get("wasm"):
                raise FileExistsError("只有可运行的 Bot 可以开始对局。")
            if not Path(bot["wasm"]).is_file() or sha_file(bot["wasm"]) != bot["wasm_sha256"]:
                raise FileExistsError("Bot 产物已改变，请重新导入。")
            result.append({k: bot[k] for k in ("id", "name", "wasm", "wasm_sha256")})
        return result

    def visible_run(identity):
        row = store.get("run", identity)
        if row.get("deleted_at"):
            raise KeyError(identity)
        return row

    def new_match(ids, map_seed, key, request_data, bot_seeds=None, entrants=None, game_id="bomberman", opening_mode="empty", rules=None):
        if game_id == "gomoku" and len(ids) != 2:
            raise ValueError("五子棋需要两个 Bot。")
        if game_id == "bomberman" and opening_mode != "empty":
            raise ValueError("炸弹人不支持棋局开局库。")
        entrants = entrants or frozen_bots(ids, game_id)
        identity = "run-" + secrets.token_hex(8)
        seed = secrets.randbits(32) if map_seed is None else map_seed
        inputs = dict(match_id=identity, entrants=entrants, map_seed=seed,
                      bot_seeds=bot_seeds or [f"{secrets.randbits(64):016x}" for _ in entrants], components=components(game_id),
                      game_id=game_id, opening_mode=opening_mode)
        if game_id == "bomberman":
            from engine.model import Rules
            inputs["rules"] = rules if rules is not None else Rules().record()
            inputs["components"] = components(game_id, Rules.from_record(inputs["rules"]).scoring_version)
        pair_runs = [identity, "run-" + secrets.token_hex(8)] if game_id == "gomoku" else None
        if pair_runs:
            inputs["legs"] = [dict(match_id=pair_runs[i], entrants=entrants if i == 0 else list(reversed(entrants)),
                                   map_seed=seed, bot_seeds=inputs["bot_seeds"] if i == 0 else list(reversed(inputs["bot_seeds"])),
                                   game_id=game_id, opening_mode=opening_mode) for i in range(2)]
        def resource(task, db):
            require_available_bots(store, ids, db)
            for index, leg in enumerate(inputs.get("legs", [inputs])):
                participants = leg["entrants"]
                store.put("run", dict(id=leg["match_id"], title=" vs ".join(e["name"] for e in participants),
                                  game_id=game_id, opening_mode=opening_mode,
                                  pair_id=identity if pair_runs else None, pair_index=index if pair_runs else None, pair_runs=pair_runs,
                                  entrants=[dict(id=e["id"], name=e["name"], slot=i, wasm_sha256=e["wasm_sha256"])
                                            for i, e in enumerate(participants)],
                                  status="pending", ticks=0, verified=False, result=None, map_seed=seed,
                                  created=utc_now(), task_id=task["id"], diagnostic=None), create=True, db=db)
        task = executor.create("match", inputs, key, request=request_data, resource=resource)
        row = store.get("run", task["inputs"]["match_id"])
        if row.get("deleted_at"):
            raise FileExistsError("该请求对应的对局已在回收站，请恢复记录或创建新对局。")
        return show_match(row)

    def show_match(row):
        value = public_match(row)
        if row.get("pair_runs"):
            legs = [store.get("run", i) for i in row["pair_runs"]]
            complete = all(r["status"] == "completed" and r.get("verified") and (r.get("result") or {}).get("valid") for r in legs)
            score = [sum(r["result"]["players"][i if index == 0 else 1-i]["placement_score"] for index, r in enumerate(legs)) for i in range(2)] if complete else None
            value["pair"] = dict(complete=complete, counted=complete and not any(r.get("deleted_at") for r in legs), score=score,
                                 runs=[dict(id=r["id"], status=r["status"], pair_index=r["pair_index"], deleted=bool(r.get("deleted_at"))) for r in legs])
        return value

    @app.post("/api/v1/matches", status_code=202)
    def create_match(body: MatchInput, request: Request):
        return new_match(body.bot_ids, body.map_seed, request.headers.get("idempotency-key"), body.model_dump(),
                         game_id=body.game_id, opening_mode=body.opening_mode)

    def new_human_match(body, key, request_data):
        bot = frozen_bots([body.bot_id], "gomoku")[0]
        human = dict(id="human", name="你", kind="human", wasm_sha256=None)
        entrants = [human, bot] if body.human_slot == 0 else [bot, human]
        identity = "run-" + secrets.token_hex(8)
        inputs = dict(match_id=identity, entrants=entrants, map_seed=0,
                      bot_seeds=[f"{secrets.randbits(64):016x}" for _ in entrants],
                      components=components("gomoku"), game_id="gomoku", opening_mode="empty",
                      mode="human", human_slot=body.human_slot)
        def resource(task, db):
            require_available_bots(store, [body.bot_id], db)
            store.put("run", dict(id=identity, title=" vs ".join(e["name"] for e in entrants),
                                 game_id="gomoku", mode="human", human_slot=body.human_slot, opening_mode="empty",
                                 entrants=[dict(id=e["id"], name=e["name"], slot=i, kind=e.get("kind", "bot"),
                                                wasm_sha256=e["wasm_sha256"]) for i, e in enumerate(entrants)],
                                 status="pending", ticks=0, verified=False, result=None, map_seed=0,
                                 created=utc_now(), task_id=task["id"], diagnostic=None, waiting_tick=None), create=True, db=db)
        task = executor.create("match", inputs, key, request=request_data, resource=resource)
        return show_match(visible_run(task["inputs"]["match_id"]))

    @app.post("/api/v1/human-matches", status_code=202)
    def create_human_match(body: HumanMatchInput, request: Request):
        return new_human_match(body, request.headers.get("idempotency-key"), body.model_dump())

    @app.post("/api/v1/matches/{identity}/actions")
    def human_move(identity: str, body: HumanAction):
        command = body.model_dump()
        def accept(row):
            if row.get("deleted_at"):
                raise KeyError(identity)
            if row.get("mode") != "human":
                raise FileExistsError("本局不是人机对局。")
            if row.get("last_human_input") == command:
                return  # A retry after a lost response must not place a second stone.
            if row["status"] != "running" or row.get("waiting_tick") != body.tick or row.get("human_input"):
                raise FileExistsError("当前不能落子，请回到最新棋盘，等待轮到你。")
            records = decode(Path(row["live_path"]).read_bytes())
            state = records[-1].get("state", records[0]["initial_state"])
            if state["reason"] or state["tick"] != body.tick or state["turn_color"] != row["human_slot"] + 1:
                raise FileExistsError("棋局已变化，请回到最新棋盘。")
            if body.action < 225 and state["grid"][body.action]:
                raise ValueError("这里已有棋子，请选择空位。")
            row.update(human_input=command, last_human_input=command)
        row = store.update("run", identity, accept)
        return show_match(row)

    @app.post("/api/v1/matches/{identity}/rerun", status_code=202)
    def rerun(identity: str, request: Request):
        original = visible_run(identity)
        inputs = store.get("task", original["task_id"])["inputs"]
        if inputs.get("mode") == "human":
            bot = inputs["entrants"][1-inputs["human_slot"]]
            return new_human_match(HumanMatchInput(bot_id=bot["id"], human_slot=inputs["human_slot"]),
                                   request.headers.get("idempotency-key"), dict(rerun=identity))
        for bot in inputs["entrants"]:
            if not Path(bot["wasm"]).is_file() or sha_file(bot["wasm"]) != bot["wasm_sha256"]:
                raise FileExistsError("原 Bot 产物已改变，无法按原输入重新运行。")
        return new_match([e["id"] for e in inputs["entrants"]], inputs["map_seed"],
                         request.headers.get("idempotency-key"), dict(rerun=identity),
                         inputs["bot_seeds"], inputs["entrants"], inputs.get("game_id", "bomberman"), inputs.get("opening_mode", "empty"),
                         inputs.get("rules", {}))

    @app.get("/api/v1/matches")
    def matches(offset: int = 0, limit: int = 30, q: str = "", status: MatchStatus | None = None,
                trashed: bool = False, game_id: Literal["bomberman", "gomoku"] | None = None):
        rows = filter_runs(store.list("run"), q=q, status=status, trashed=trashed, game_id=game_id)
        rows.sort(key=lambda r: (r["created"], r["id"]), reverse=True)
        limit, offset = max(1, min(limit, 100)), max(0, offset)
        return dict(items=[show_match(r) for r in rows[offset:offset + limit]], total=len(rows))

    @app.post("/api/v1/matches/manage")
    def manage_matches(body: MatchManagement):
        return manage_runs(store, body.action, body.ids, all_finished=body.all_finished,
                           q=body.q, status=body.status, game_id=body.game_id)

    @app.patch("/api/v1/matches/{identity}")
    def rename_match(identity: str, body: MatchTitle):
        title = body.title.strip()
        if not title:
            raise ValueError("对局名称不能为空。")
        def change(row):
            if row.get("deleted_at"):
                raise KeyError(identity)
            row["title"] = title
        row = store.update("run", identity, change)
        store.emit(identity, "run", dict(status=row["status"]))
        return show_match(row)

    @app.get("/api/v1/matches/{identity}")
    def match(identity: str):
        return show_match(visible_run(identity))

    @app.get("/api/v1/matches/{identity}/frames")
    def frames(identity: str, after_seq: int = -1, attempt_id: str | None = None):
        row = visible_run(identity)
        partial = row["status"] in ("pending", "running")
        path = Path(row.get("live_path", ""))
        ui = dict(frames=[], result=None, partial=partial)
        if path.is_file():
            data = path.read_bytes()
            if row.get("verified") and row.get("source_sha256"):
                import hashlib
                if hashlib.sha256(data).hexdigest() != row["source_sha256"]:
                    raise APIError("recording_changed", "录像文件已损坏或改变，无法读取原运行。", 409)
            last = data.rfind(b"\n")
            if last >= 0:
                ui = project(decode(data[:last + 1]), partial=True)
        elif row.get("verified"):
            raise APIError("recording_missing", "录像文件缺失，请检查本机数据目录。", 409)
        ui["partial"] = partial
        # The persisted terminal run, after world verification, authorizes a result.
        if not row.get("verified"):
            ui.update(result=None, verified=False)
        ui.update(attempt_id=identity, last_seq=len(ui["frames"]) - 1,
                  resync_required=bool((attempt_id and attempt_id != identity) or after_seq > len(ui["frames"]) - 1))
        if ui["resync_required"]:
            after_seq = -1
        ui["frames"] = [frame for frame in ui["frames"] if frame["seq"] > after_seq]
        return ui

    @app.get("/api/v1/leaderboard")
    def rankings(game_id: Literal["bomberman", "gomoku"] = "bomberman"):
        return leaderboard(store.list("bot"), filter_runs(store.list("run")), game_id)

    @app.get("/api/v1/events")
    async def events(request: Request, after: int | None = None):
        try:
            last = request.headers.get("last-event-id")
            cursor = (max(after or 0, int(last or "0")) if after is not None or last is not None
                      else await asyncio.to_thread(store.event_watermark))
        except ValueError:
            raise APIError("invalid_cursor", "事件序号无效。", 422)
        async def stream():
            nonlocal cursor
            while not await request.is_disconnected():
                rows = await asyncio.to_thread(store.events, cursor)
                for event in rows:
                    cursor = event["event_id"]
                    notice = {k: event[k] for k in ("event_id", "resource_id", "type")}
                    notice["payload"] = {k: event["payload"][k] for k in ("status", "seq", "type") if k in event["payload"]}
                    yield f"id: {cursor}\ndata: {json.dumps(notice)}\n\n"
                if not rows:
                    yield ": keepalive\n\n"
                await asyncio.sleep(.4)
        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    @app.get("/{path:path}")
    def frontend(path: str):
        if path.startswith("api/"):
            raise APIError("not_found", "接口不存在。", 404)
        dist = ROOT / "web/dist"
        candidate = (dist / path).resolve()
        if candidate.is_relative_to(dist.resolve()) and candidate.is_file():
            return FileResponse(candidate)
        if (dist / "index.html").exists():
            return FileResponse(dist / "index.html")
        return JSONResponse(dict(status="frontend_not_built", message="请先在 web 目录执行 npm run build。"), status_code=503)

    return app
