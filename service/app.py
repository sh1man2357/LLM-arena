"""Same-origin local spectator API and static application host."""
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import secrets
from urllib.parse import urlparse

from fastapi import FastAPI, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from runner.io import ROOT, read_json
from service import APP_VERSION
from service.imports import import_bundled, import_replay
from service.replays import MAX_REPLAY_BYTES, decode, project
from service.store import Store


class APIError(Exception):
    def __init__(self, code, message, status=400):
        self.code, self.message, self.status = code, message, status


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ImportInput(Input):
    source: str = "bundled-v0.1"


def public_match(row):
    return {k: row.get(k) for k in ("id", "title", "tournament_id", "entrants", "status", "ticks", "result", "verified",
                                    "disclosure", "created", "case_index", "swapped", "source_sha256", "attempt_id")}


def public_tournament(row):
    return {k: row.get(k) for k in ("id", "title", "status", "disclosure", "official", "report", "expected_matches",
                                    "completed_matches", "created", "source_sha256", "job_id", "submission_window_closed")}


def public_entrant(row):
    return {k: row.get(k) for k in ("id", "name", "model", "wasm_sha256", "status", "baseline", "created", "submission_id")}


def create_app(data_root=None, *, demo=False, workers=False):
    store = Store(data_root or os.environ.get("ARENA_DATA", str(ROOT / "artifacts/local")))

    @asynccontextmanager
    async def lifespan(app):
        if demo:
            await asyncio.to_thread(import_bundled, store)
        yield

    app = FastAPI(title="LLM Arena local API", version=APP_VERSION, lifespan=lifespan)
    app.state.store = store

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

    @app.get("/api/v1/matches")
    def matches(request: Request, tournament_id: str | None = None, entrant: str | None = None,
                status: str | None = None, reason: str | None = None, offset: int = 0, limit: int = 30, q: str = ""):
        rows = store.list("match")
        rows = [r for r in rows if r.get("disclosure") != "sealed" or request.cookies.get("arena_owner") == store.token]
        rows = [r for r in rows if (not tournament_id or r.get("tournament_id") == tournament_id)
                and (not entrant or entrant in [e["id"] for e in r["entrants"]]) and (not status or r["status"] == status)
                and (not reason or (r.get("result") or {}).get("reason") == reason) and q.lower() in r["title"].lower()]
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
                        and m.get("case", {}).get("pair") == case["pair"]
                        and m.get("case", {}).get("case_index") == case["case_index"] and m["id"] != identity]
            response["swap_match_id"] = siblings[0]["id"] if siblings else None
        return response

    @app.get("/api/v1/matches/{identity}/frames")
    def frames(identity: str, request: Request, after_seq: int = -1):
        row = visible(store.get("match", identity), request)
        if row.get("projection") and Path(row["projection"]).exists():
            ui = read_json(row["projection"])
        else:
            path = Path(row.get("live_path", ""))
            if not path.is_file():
                return dict(frames=[], partial=True, attempt_id=row["attempt_id"])
            data = path.read_bytes()
            last = data.rfind(b"\n")
            ui = project(decode(data[:last+1]), partial=True) if last >= 0 else dict(frames=[])
        response = dict(ui)
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

    @app.post("/api/v1/imports")
    async def imports(body: ImportInput, request: Request):
        owner(request)
        if body.source != "bundled-v0.1":
            raise APIError("invalid_source", "只能选择预注册的参考归档；上传 Replay 使用文件导入。", 422)
        row = await asyncio.to_thread(import_bundled, store)
        return public_tournament(row)

    @app.post("/api/v1/imports/replay")
    async def upload_replay(file: UploadFile, request: Request):
        owner(request)
        data = await file.read(MAX_REPLAY_BYTES+1)
        if len(data) > MAX_REPLAY_BYTES:
            raise APIError("upload_too_large", "Replay 超过 16 MiB。", 413)
        row = await asyncio.to_thread(import_replay, store, data)
        return public_match(row)

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
                    data = json.dumps({k: event[k] for k in ("event_id", "resource_id", "type")})
                    yield f"id: {cursor}\ndata: {data}\n\n"
                if not rows:
                    yield ": keepalive\n\n"
                await asyncio.sleep(.4)
        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    @app.get("/api/v1/exports/{identity}")
    def export(identity: str, request: Request, kind: str = "replay"):
        if kind == "report":
            row = visible(store.get("tournament", identity), request)
            if not row.get("report") or row["report"]["status"] != "complete":
                raise APIError("incomplete_report", "不完整批次没有正式报告。", 409)
            data = json.dumps(row["report"], ensure_ascii=False, indent=2)
        else:
            row = visible(store.get("match", identity), request)
            if not row.get("projection"):
                raise APIError("running_match", "对局完成后才能导出。", 409)
            data = json.dumps(read_json(row["projection"]), ensure_ascii=False)
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
