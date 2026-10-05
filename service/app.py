"""Same-origin local spectator API and static application host."""
import asyncio
from contextlib import asynccontextmanager
import json
import hashlib
import os
from pathlib import Path
import secrets
from typing import Literal
from urllib.parse import urlparse

from fastapi import FastAPI, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from runner.io import ROOT, read_json
from service import APP_VERSION
from service.analysis import summarize
from service.imports import import_bundled, import_replay, MAX_ARCHIVE_BYTES
from service.publication import close_submissions, publish_tournament, published_file, public_bytes
from service.replays import MAX_REPLAY_BYTES, decode, project
from service.store import Store
from service.submissions import create_session, session_view, submit
from service.jobs import Queue
from runner.match import components
from runner.tournament import validate_cases, schedule
from engine.maps import generate


class APIError(Exception):
    def __init__(self, code, message, status=400):
        self.code, self.message, self.status = code, message, status


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ImportInput(Input):
    source: str = "bundled-v0.1"


class SessionInput(Input):
    name: str = Field(min_length=1, max_length=100)
    model: str = Field(default="未注明模型", max_length=160)
    started_at: str | None = None
    time_source: Literal["host_confirmation", "external_record"] = "host_confirmation"


class SubmitInput(Input):
    source: str = Field(min_length=1)
    received_at: str | None = None


class MatchInput(Input):
    entrant_ids: list[str] = Field(min_length=2, max_length=2)
    map_seed: int = Field(default=1, ge=0, le=4294967295)
    title: str = Field(default="双人对局", max_length=120)
    tick_interval_ms: Literal[0, 50, 250] = 50


class TournamentInput(Input):
    entrant_ids: list[str] = Field(min_length=2, max_length=16)
    case_count: int = Field(default=50, ge=1, le=1000)
    title: str = Field(default="新一轮策略竞技", max_length=120)
    official: bool = False


def public_job(row):
    result = {k: row.get(k) for k in ("id", "kind", "status", "progress", "total", "created", "started", "finished", "attempt_id", "attempts", "diagnostic", "result")}
    result["resources"] = {k: row["inputs"][k] for k in ("submission_id", "match_id", "tournament_id", "title") if k in row["inputs"]}
    return result


def public_submission(row):
    return {k: row.get(k) for k in ("id", "session_id", "name", "model", "source_sha256", "wasm_sha256", "received_at", "frozen_at", "time_source", "late", "status", "created", "compile_log", "qualification", "diagnostic", "entrant_id", "job_id")}


def public_match(row):
    response = {k: row.get(k) for k in ("id", "title", "tournament_id", "entrants", "status", "ticks", "result", "verified",
                                    "disclosure", "created", "case_index", "swapped", "source_sha256", "attempt_id",
                                    "source_format", "origin_source_sha256", "bot_rerunnable", "failure_reason")}
    if row.get("case"):
        response.update(case_index=row['case']['case_index'], swapped=row['case']['swapped'])
    return response


def public_tournament(row):
    result = {k: row.get(k) for k in ("id", "title", "status", "disclosure", "official", "report", "expected_matches",
                                    "completed_matches", "created", "source_sha256", "job_id", "submission_window_closed",
                                    "window_closed_at", "published_at", "publication_id", "publication_sha256", "imported", "bundled_reference",
                                    "requires_disclosure_confirmation", "window_close_source", "window_closed_entrants")}
    result["bundled_reference"] = bool(row.get("bundled_reference") or row["id"] == "reference-v01")
    return result


def public_entrant(row):
    return {k: row.get(k) for k in ("id", "name", "model", "wasm_sha256", "status", "baseline", "created", "submission_id")}


def create_app(data_root=None, *, demo=False, workers=False):
    store = Store(data_root or os.environ.get("ARENA_DATA", str(ROOT / "artifacts/local")))
    queue = Queue(store)

    @asynccontextmanager
    async def lifespan(app):
        if workers:
            queue.start()
        if demo:
            if workers:
                try:
                    store.get("tournament", "reference-v01")
                except KeyError:
                    queue.create("import", {}, key="bundled-reference-v01")
            else:
                await asyncio.to_thread(import_bundled, store)
        try:
            yield
        finally:
            if workers:
                queue.stop()

    app = FastAPI(title="LLM Arena local API", version=APP_VERSION, lifespan=lifespan)
    app.state.store = store
    app.state.queue = queue

    def owner(request):
        cookie = request.cookies.get("arena_owner", "")
        if not secrets.compare_digest(cookie, store.token):
            raise APIError("owner_required", "请先进入主办方工作台。", 403)

    def visible(row, request):
        if row.get("disclosure") == "sealed":
            owner(request)
        return row

    @app.middleware("http")
    async def local_boundary(request, call_next):
        host = urlparse("http://" + request.headers.get("host", "")).hostname
        if host not in ("127.0.0.1", "localhost", "testserver"):
            return JSONResponse(dict(code="invalid_host", message="服务仅接受本机 Host。"), status_code=403)
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
            return JSONResponse(dict(code="invalid_origin", message="不接受外部来源请求。"), status_code=403)
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse(dict(code="invalid_origin", message="不接受跨站请求。"), status_code=403)
        if (request.method not in ("GET", "HEAD", "OPTIONS") and request.url.path != "/api/v1/admin/unlock"
                and request.cookies.get("arena_owner") != store.token):
            return JSONResponse(dict(code="owner_required", message="请先进入主办方工作台。"), status_code=403)
        if request.method not in ("GET", "HEAD", "OPTIONS") and any(
                j["kind"] == "backup" and j["status"] == "running" for j in store.list("job")):
            return JSONResponse(dict(code="backup_in_progress", message="正在固定私有备份，请稍后再修改数据；观赛仍可继续。"), status_code=423)
        length = request.headers.get("content-length")
        if length and (not length.isdigit() or int(length) > 18 * 1024 * 1024):
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
        return JSONResponse(dict(code="frozen_conflict", message=str(exc)), status_code=409)

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse(dict(code="invalid_evidence", message=str(exc)), status_code=422)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, exc):
        return JSONResponse(dict(code="invalid_input", message="输入字段无效。", details=str(exc)), status_code=422)

    @app.get("/health")
    def health():
        import platform
        return dict(status="ready", app_version=APP_VERSION, ruleset="1", runtime="wasmtime-49.0.0",
                    python=platform.python_version(), frontend_ready=(ROOT / "web/dist/index.html").exists())

    @app.post("/api/v1/admin/unlock")
    def unlock(request: Request):
        if request.headers.get("x-arena-local") != "1":
            raise APIError("local_intent_required", "请从本地工作台进入。", 403)
        response = JSONResponse(dict(status="owner"))
        response.set_cookie("arena_owner", store.token, httponly=True, samesite="strict")
        return response

    @app.get("/api/v1/entrants")
    def entrants():
        return dict(items=[public_entrant(r) for r in store.list("entrant")])

    @app.get("/api/v1/entrants/{identity}")
    def entrant(identity: str):
        return public_entrant(store.get("entrant", identity))

    @app.get("/api/v1/sessions")
    def sessions(request: Request):
        owner(request)
        return dict(items=[session_view(r) for r in store.list("session")])

    @app.post("/api/v1/sessions", status_code=201)
    def new_session(body: SessionInput, request: Request):
        owner(request)
        return create_session(store, body.name, body.model, body.started_at, body.time_source, request.headers.get("idempotency-key"))

    @app.get("/api/v1/sessions/{identity}")
    def get_session(identity: str, request: Request):
        owner(request)
        return session_view(store.get("session", identity))

    @app.post("/api/v1/sessions/{identity}/submit", status_code=201)
    def final_submit(identity: str, body: SubmitInput, request: Request):
        owner(request)
        if len(body.source.encode("utf-8")) > 1024 * 1024:
            raise APIError("source_too_large", "源码超过 1 MiB。", 413)
        return public_submission(submit(store, identity, body.source, received_at=body.received_at))

    @app.get("/api/v1/submissions")
    def submissions(request: Request):
        owner(request)
        return dict(items=[public_submission(r) for r in store.list("submission")])

    @app.get("/api/v1/submissions/{identity}")
    def submission(identity: str, request: Request):
        owner(request)
        return public_submission(store.get("submission", identity))

    @app.get("/api/v1/submissions/{identity}/source")
    def source(identity: str, request: Request):
        owner(request)
        row = store.get("submission", identity)
        return Response(Path(row["source"]).read_text(encoding="utf-8"), media_type="text/plain")

    @app.post("/api/v1/submissions/{identity}/compile", status_code=202)
    def compile_bot(identity: str, request: Request):
        owner(request)
        row = store.get("submission", identity)
        if row["late"]:
            raise APIError("late_submission", "源码逾期，保留记录但不进入本次正式参赛。", 409)
        return public_job(queue.create("compile", dict(submission_id=identity, components=components()), request.headers.get("idempotency-key")))

    def frozen_entrants(ids):
        if len(set(ids)) != len(ids):
            raise ValueError("Select distinct entrants")
        entrants = []
        for eid in sorted(ids):
            value = store.get("entrant", eid)
            if value["status"] != "qualified" or not value.get("wasm"):
                raise FileExistsError("Only qualified frozen entrants can compete")
            entrants.append(dict(id=eid, wasm=value["wasm"], wasm_sha256=value["wasm_sha256"]))
        return entrants

    @app.post("/api/v1/matches", status_code=202)
    def create_match(body: MatchInput, request: Request):
        owner(request)
        entrants = frozen_entrants(body.entrant_ids)
        identity = "m-" + secrets.token_hex(8)
        inputs = dict(match_id=identity, title=body.title, entrants=entrants, map_seed=body.map_seed,
                      bot_seeds=[f"{secrets.randbits(64):016x}" for _ in range(2)], components=components(), tick_interval_ms=body.tick_interval_ms)
        key = request.headers.get("idempotency-key")
        def resource(job, db):
            store.put("match", dict(id=identity, title=body.title, tournament_id=None,
                                     entrants=[dict(id=e["id"], slot=i, wasm_sha256=e["wasm_sha256"]) for i,e in enumerate(entrants)],
                                     status="queued", ticks=0, verified=False, disclosure="disclosed", result=None,
                                     attempt_id="pending", created=job["created"]), create=True, db=db)
        return public_job(queue.create("match", inputs, key, request=body.model_dump(), resource=resource))

    @app.post("/api/v1/tournaments", status_code=202)
    def create_tournament(body: TournamentInput, request: Request):
        owner(request)
        entrants = frozen_entrants(body.entrant_ids)
        key = request.headers.get("idempotency-key")
        cases, hashes = [], set()
        while len(cases) < body.case_count:
            seed = secrets.randbits(32)
            generated = generate(seed)
            if generated["map_hash"] in hashes:
                continue
            hashes.add(generated["map_hash"])
            cases.append(dict(map_seed=seed, bot_seeds=[f"{secrets.randbits(64):016x}" for _ in range(2)]))
        validate_cases(cases)
        identity = "t-" + secrets.token_hex(8)
        inputs = dict(tournament_id=identity, title=body.title, entrants=entrants, cases=cases,
                      components=components(), request=body.model_dump())
        def resource(job, db):
            store.put("tournament", dict(id=identity, title=body.title, official=body.official, status="queued",
                                     disclosure="sealed" if body.official else "disclosed", report=None,
                                     expected_matches=len(schedule(entrants, cases)), completed_matches=0,
                                     submission_window_closed=False, job_id=job["id"], created=job["created"]), create=True, db=db)
        job = queue.create("tournament", inputs, key, request=body.model_dump(), resource=resource)
        return public_job(job)

    @app.get("/api/v1/jobs")
    def jobs(request: Request):
        owner(request)
        return dict(items=[public_job(r) for r in store.list("job")])

    @app.get("/api/v1/jobs/{identity}")
    def get_job(identity: str, request: Request):
        owner(request)
        return public_job(store.get("job", identity))

    @app.get("/api/v1/jobs/{identity}/log")
    def job_log(identity: str, request: Request, attempt_id: str | None = None):
        owner(request)
        row = store.get("job", identity)
        attempt = attempt_id or row.get("attempt_id")
        if attempt_id and attempt_id not in [a["id"] for a in row["attempts"]]:
            raise APIError("unknown_attempt", "该作业没有此执行尝试。", 404)
        path = store.root / "jobs" / identity / f"{attempt}.log"
        content = path.read_text(encoding="utf-8", errors="replace")[-1024*1024:] if path.is_file() else "尚无执行日志。"
        return Response(content, media_type="text/plain")

    @app.post("/api/v1/jobs/{identity}/stop")
    def stop_job(identity: str, request: Request):
        owner(request)
        return public_job(queue.request_stop(identity))

    @app.post("/api/v1/jobs/{identity}/resume")
    def resume_job(identity: str, request: Request):
        owner(request)
        return public_job(queue.resume(identity))

    @app.get("/api/v1/matches")
    def matches(request: Request, tournament_id: str | None = None, entrant: str | None = None,
                status: str | None = None, reason: str | None = None, offset: int = 0, limit: int = 30, q: str = "",
                opponent: str | None = None, case_index: int | None = None):
        rows = store.list("match")
        rows = [r for r in rows if r.get("disclosure") != "sealed" or request.cookies.get("arena_owner") == store.token]
        rows = [r for r in rows if (not tournament_id or r.get("tournament_id") == tournament_id)
                and (not entrant or entrant in [e["id"] for e in r["entrants"]]) and (not status or r["status"] == status)
                and (not reason or (r.get("result") or {}).get("reason") == reason) and q.lower() in r["title"].lower()
                and (not opponent or opponent in [e["id"] for e in r["entrants"]])
                and (case_index is None or (r.get("case") or {}).get("case_index") == case_index)]
        limit, offset = max(1, min(limit, 100)), max(0, offset)
        return dict(items=[public_match(r) for r in rows[offset:offset+limit]], total=len(rows), offset=offset, limit=limit)

    @app.get("/api/v1/matches/{identity}")
    def match(identity: str, request: Request):
        row = visible(store.get("match", identity), request)
        response = public_match(row)
        if row.get("case"):
            case = row["case"]
            response.update(case_index=case["case_index"], swapped=case["swapped"])
            siblings = [m for m in store.list("match") if m.get("tournament_id") == row.get("tournament_id")
                        and (m.get("case") or {}).get("pair") == case["pair"]
                        and (m.get("case") or {}).get("case_index") == case["case_index"] and m["id"] != identity]
            response["swap_match_id"] = siblings[0]["id"] if siblings else None
        return response

    @app.get("/api/v1/matches/{identity}/frames")
    def frames(identity: str, request: Request, after_seq: int = -1, attempt_id: str | None = None):
        row = visible(store.get("match", identity), request)
        if row.get("projection") and Path(row["projection"]).exists():
            ui = read_json(row["projection"])
        else:
            path = Path(row.get("live_path", ""))
            if not path.is_file():
                return dict(frames=[], partial=True, attempt_id=row["attempt_id"], last_seq=-1,
                            resync_required=bool(attempt_id and attempt_id != row["attempt_id"]))
            data = path.read_bytes()
            last = data.rfind(b"\n")
            ui = project(decode(data[:last+1]), partial=True) if last >= 0 else dict(frames=[])
        response = dict(ui)
        if not row.get("replay") and row["status"] != "completed" and (response.get("result") or {}).get("valid"):
            response.update(partial=True, result=None, verified=False)
        response["last_seq"] = len(ui["frames"])-1
        response["resync_required"] = bool((attempt_id and attempt_id != row["attempt_id"]) or after_seq > response["last_seq"])
        if response["resync_required"]:
            after_seq = -1
        response["frames"] = [f for f in ui["frames"] if f["seq"] > after_seq]
        response["attempt_id"] = row["attempt_id"]
        return response

    @app.get("/api/v1/tournaments")
    def tournaments(request: Request):
        return dict(items=[public_tournament(r) for r in store.list("tournament")
                           if r.get("disclosure") != "sealed" or request.cookies.get("arena_owner") == store.token])

    @app.get("/api/v1/tournaments/{identity}")
    def tournament(identity: str, request: Request):
        return public_tournament(visible(store.get("tournament", identity), request))

    @app.get("/api/v1/tournaments/{identity}/report")
    def report(identity: str, request: Request):
        row = visible(store.get("tournament", identity), request)
        return row.get("report") or dict(status="incomplete", pairs=[], entrants=[])

    @app.get("/api/v1/tournaments/{identity}/analysis")
    def analysis(identity: str, request: Request):
        visible(store.get("tournament", identity), request)
        return summarize([m for m in store.list("match") if m.get("tournament_id") == identity])

    @app.post("/api/v1/imports", status_code=202)
    async def imports(body: ImportInput, request: Request):
        owner(request)
        if body.source != "bundled-v0.1":
            raise APIError("invalid_source", "只能选择预注册的参考归档；上传 Replay 使用文件导入。", 422)
        return public_job(queue.create("import", {}, request.headers.get("idempotency-key")))

    @app.get("/api/v1/backups")
    def backups(request: Request):
        owner(request)
        return dict(items=[{k: r[k] for k in ("id", "created", "sha256", "size", "files", "records", "contains_private_inputs")}
                           for r in store.list("backup")])

    @app.post("/api/v1/backups", status_code=202)
    def backup(request: Request):
        owner(request)
        return public_job(queue.create("backup", {}, request.headers.get("idempotency-key")))

    @app.get("/api/v1/backups/{identity}")
    def download_backup(identity: str, request: Request):
        owner(request)
        from runner.io import sha_file
        row = store.get("backup", identity)
        if not Path(row["path"]).is_file() or sha_file(row["path"]) != row["sha256"]:
            raise FileExistsError("Private backup is missing or changed; create a new verified backup")
        return FileResponse(row["path"], media_type="application/zip", filename=f"{identity}.zip")

    @app.post("/api/v1/imports/replay")
    async def upload_replay(file: UploadFile, request: Request):
        owner(request)
        data = await file.read(MAX_REPLAY_BYTES+1)
        if len(data) > MAX_REPLAY_BYTES:
            raise APIError("upload_too_large", "Replay 超过 16 MiB。", 413)
        row = await asyncio.to_thread(import_replay, store, data)
        return public_match(row)

    @app.post("/api/v1/imports/archive", status_code=202)
    async def upload_archive(file: UploadFile, request: Request, title: str = "导入的比赛批次"):
        owner(request)
        if not 1 <= len(title) <= 120:
            raise APIError("invalid_title", "批次名称须为 1～120 字符。", 422)
        data = await file.read(MAX_ARCHIVE_BYTES + 1)
        if len(data) > MAX_ARCHIVE_BYTES:
            raise APIError("upload_too_large", "ZIP 归档超过 16 MiB。", 413)
        source_hash = hashlib.sha256(data).hexdigest()
        folder = store.root / "uploads"
        folder.mkdir(exist_ok=True)
        path = folder / f"{source_hash}.zip"
        if not path.exists():
            # Atomic registration: the worker never reads a partly uploaded file.
            temporary = folder / f"{secrets.token_hex(16)}.tmp"
            temporary.write_bytes(data)
            os.replace(temporary, path)
        inputs = dict(archive=str(path), source_sha256=source_hash, title=title,
                      tournament_id="archive-" + source_hash[:20])
        return public_job(queue.create("import", inputs, request.headers.get("idempotency-key")))

    @app.post("/api/v1/tournaments/{identity}/close-submissions")
    def close_window(identity: str, request: Request):
        owner(request)
        return public_tournament(close_submissions(store, identity))

    @app.post("/api/v1/tournaments/{identity}/publish")
    def publish(identity: str, request: Request):
        owner(request)
        return public_tournament(publish_tournament(store, identity))

    @app.get("/api/v1/events")
    async def events(request: Request, after: int = 0):
        try:
            cursor = max(after, int(request.headers.get("last-event-id", "0")))
        except ValueError:
            raise APIError("invalid_cursor", "事件序号无效。", 422)
        async def stream():
            nonlocal cursor
            while not await request.is_disconnected():
                rows = await asyncio.to_thread(store.events, cursor)
                for event in rows:
                    cursor = event["event_id"]
                    # Notification contains identifiers only; detail reads enforce disclosure / owner access.
                    notice = {k: event[k] for k in ("event_id", "resource_id", "type")}
                    notice["payload"] = {k: event["payload"][k] for k in ("status", "progress", "seq", "attempt_id", "type") if k in event["payload"]}
                    notice.update(attempt_id=notice["payload"].get("attempt_id"), seq=notice["payload"].get("seq"))
                    data = json.dumps(notice)
                    yield f"id: {cursor}\ndata: {data}\n\n"
                if not rows:
                    yield ": keepalive\n\n"
                await asyncio.sleep(.4)
        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    @app.get("/api/v1/exports/{identity}")
    def export(identity: str, request: Request, kind: Literal["replay", "report", "publication"] = "replay"):
        if kind in ("report", "publication"):
            row = visible(store.get("tournament", identity), request)
            if row.get("publication_id"):
                return FileResponse(published_file(store, row, kind), media_type="application/json", filename=f"{identity}-{kind}.json")
            if kind == "publication":
                raise APIError("not_published", "发布后才能导出固定的证据清单。", 409)
            if not row.get("report") or row["report"]["status"] != "complete":
                raise APIError("incomplete_report", "不完整批次没有正式报告。", 409)
            data = public_bytes(row["report"])
        else:
            row = visible(store.get("match", identity), request)
            if row.get("publication_id"):
                return FileResponse(published_file(store, row, kind), media_type="application/json", filename=f"{identity}-replay.json")
            if not row.get("projection"):
                raise APIError("running_match", "对局完成后才能导出。", 409)
            data = public_bytes(read_json(row["projection"]))
        return Response(data, media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{identity}-{kind}.json"'})

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
