import base64
from datetime import UTC, datetime
from hashlib import sha256

from fastapi import Depends, FastAPI, Header, HTTPException, Request, File, UploadFile
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.app.errors import ApiError
from backend.app.rate_limit import RateLimiter
from poc.wechat import ClipError


MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024  # 20 MiB


class ClipRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


class RegisterRequest(BaseModel):
    invite_code: str = Field(min_length=1, max_length=128)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class AckRequest(BaseModel):
    note_ids: list[str] = Field(min_length=0, max_length=200)


def create_app(service, rate_limiter: RateLimiter | None = None) -> FastAPI:
    app = FastAPI()
    limiter = rate_limiter or RateLimiter()

    @app.middleware("http")
    async def limit_requests(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit():
            limit = MAX_ATTACHMENT_BYTES if request.url.path == "/v1/clips/files" else 20_480
            if int(content_length) > limit:
                return JSONResponse(status_code=413, content={"message": "请求体过大"})
        client_ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown").rsplit(",", 1)[-1].strip()
        path = request.url.path
        if path in {"/v1/auth/login", "/v1/auth/register"}:
            key, limit, window = f"auth:{client_ip}", 10, 300
        elif path.startswith("/v1/sync/"):
            token = request.headers.get("authorization", "")
            key, limit, window = f"sync:{sha256(token.encode()).hexdigest()}", 30, 60
        elif request.method == "POST" and (
            path in {"/v1/clips", "/v1/clips/files"} or path.endswith("/retry")
        ):
            token = request.headers.get("authorization", "")
            key, limit, window = f"work:{sha256(token.encode()).hexdigest()}", 20, 60
        else:
            return await call_next(request)
        if not limiter.allow(key, limit=limit, window_seconds=window):
            return JSONResponse(status_code=429, content={"message": "请求过于频繁，请稍后再试"})
        return await call_next(request)

    @app.exception_handler(ApiError)
    def handle_api_error(_, error: ApiError):
        return JSONResponse(status_code=error.status_code, content={"message": str(error)})

    @app.exception_handler(ClipError)
    def handle_clip_error(_, error: ClipError):
        return JSONResponse(status_code=400, content={"stage": error.stage, "message": str(error)})

    def require_user(authorization: str = Header(default="")) -> str:
        if not authorization.startswith("Bearer "):
            raise HTTPException(401, "需要登录")
        return service.current_user(authorization.removeprefix("Bearer ").strip())

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.post("/v1/auth/register", status_code=201)
    def register(payload: RegisterRequest):
        return service.register(payload.invite_code, payload.email, payload.password)

    @app.post("/v1/auth/login")
    def login(payload: LoginRequest):
        return service.login(payload.email, payload.password)

    @app.get("/v1/invites")
    def invite_permission(user_id: str = Depends(require_user)):
        return {"can_create": service.can_create_invites(user_id)}

    @app.post("/v1/invites", status_code=201)
    def create_invite(user_id: str = Depends(require_user)):
        return service.create_invite(user_id)

    @app.post("/v1/clips", status_code=201)
    def create_clip(payload: ClipRequest, user_id: str = Depends(require_user)):
        return service.create_clip(user_id, payload.url)

    @app.get("/v1/clips")
    def list_clips(user_id: str = Depends(require_user)):
        return service.list_clips(user_id)

    @app.post("/v1/clips/{task_id}/retry")
    def retry_clip(task_id: str, user_id: str = Depends(require_user)):
        return service.retry_clip(user_id, task_id)

    @app.post("/v1/clips/files", status_code=201)
    async def upload_file(
        file: UploadFile = File(...),
        user_id: str = Depends(require_user),
    ):
        """客户端直传附件，文件字节 base64 编码存 notes 表（kind=attachment），等插件拉取。"""
        content = await file.read()
        if not content:
            raise HTTPException(400, "文件内容不能为空")
        if len(content) > MAX_ATTACHMENT_BYTES:
            raise HTTPException(413, "文件过大")
        filename = file.filename or "attachment"
        mime = file.content_type or "application/octet-stream"
        b64data = base64.b64encode(content).decode("ascii")
        return service.create_attachment_note(user_id, filename, mime, b64data)

    # ---------- Obsidian 插件同步接口 ----------

    @app.get("/v1/sync/changes")
    def sync_changes(
        user_id: str = Depends(require_user),
        since: str | None = None,
        limit: int = 50,
    ):
        """插件增量拉取：返回 created > since 且 delivered=false 的 notes（按 created 升序）。

        响应里的 note 不含 attachment_b64，附件字节通过 /v1/sync/notes/{id}/attachment 单独下载，
        以避免单次响应过大。
        """
        if limit < 1 or limit > 200:
            limit = 50
        since_iso = since or "1970-01-01T00:00:00Z"
        notes = service.list_pending_notes(user_id, since_iso, limit=limit)
        return {
            "notes": notes,
            "server_time": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }

    @app.post("/v1/sync/ack")
    def sync_ack(payload: AckRequest, user_id: str = Depends(require_user)):
        """插件确认已写入 Vault 的 note_ids，服务端标记 delivered 并清空 attachment_b64。"""
        acked = service.ack_notes(user_id, payload.note_ids)
        return {"acked": acked}

    @app.get("/v1/sync/notes/{note_id}/attachment")
    def sync_attachment(note_id: str, user_id: str = Depends(require_user)):
        """流式返回附件原始字节（仅 kind=attachment 且属主匹配）。"""
        record = service.get_note_for_user(user_id, note_id)
        b64data = record.get("attachment_b64") or ""
        if not b64data:
            raise HTTPException(404, "附件字节不存在或已被清理")
        content = base64.b64decode(b64data)
        mime = record.get("attachment_mime") or "application/octet-stream"
        return Response(content=content, media_type=mime)

    from pathlib import Path
    static_dir = Path(__file__).parent.parent / "static"
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app
