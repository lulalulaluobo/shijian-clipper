from hashlib import sha256

from fastapi import Depends, FastAPI, Header, HTTPException, Request, File, UploadFile, Form
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.app.errors import ApiError
from backend.app.rate_limit import RateLimiter
from poc.wechat import ClipError


class ClipRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


class FnsSettingsRequest(BaseModel):
    config: str | None = Field(default=None, max_length=16_384)
    target_dir: str = Field(min_length=1, max_length=512)
    attachment_dir: str | None = Field(default=None, max_length=512)



class RegisterRequest(BaseModel):
    invite_code: str = Field(min_length=1, max_length=128)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


def create_app(service, rate_limiter: RateLimiter | None = None) -> FastAPI:
    app = FastAPI()
    limiter = rate_limiter or RateLimiter()

    @app.middleware("http")
    async def limit_requests(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit():
            limit = 20 * 1024 * 1024 if request.url.path == "/v1/clips/attachments" else 20_480
            if int(content_length) > limit:
                return JSONResponse(status_code=413, content={"message": "请求体过大"})
        client_ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown").rsplit(",", 1)[-1].strip()
        path = request.url.path
        if path in {"/v1/auth/login", "/v1/auth/register"}:
            key, limit, window = f"auth:{client_ip}", 10, 300
        elif request.method == "POST" and (
            path in {"/v1/settings/fns/check", "/v1/clips", "/v1/clips/attachments"} or path.endswith("/retry")
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

    @app.get("/v1/settings/fns")
    def get_fns_settings(user_id: str = Depends(require_user)):
        return service.get_fns_settings(user_id)

    @app.put("/v1/settings/fns")
    def save_fns_settings(payload: FnsSettingsRequest, user_id: str = Depends(require_user)):
        return service.save_fns_settings(user_id, payload.config, payload.target_dir, payload.attachment_dir)


    @app.post("/v1/settings/fns/check")
    def check_fns_settings(user_id: str = Depends(require_user)):
        return service.check_fns_settings(user_id)

    @app.post("/v1/clips", status_code=201)
    def create_clip(payload: ClipRequest, user_id: str = Depends(require_user)):
        return service.create_clip(user_id, payload.url)

    @app.get("/v1/clips")
    def list_clips(user_id: str = Depends(require_user)):
        return service.list_clips(user_id)

    @app.post("/v1/clips/{task_id}/retry")
    def retry_clip(task_id: str, user_id: str = Depends(require_user)):
        return service.retry_clip(user_id, task_id)

    @app.post("/v1/clips/attachments", status_code=201)
    async def upload_attachment(
        file: UploadFile = File(...),
        target_path: str | None = Form(default=None),
        user_id: str = Depends(require_user),
    ):
        config = service.decrypt_fns_config(user_id)
        content = await file.read()
        
        from backend.app.attachment_service import relay_attachment
        from poc.fns import _safe_filename, FnsConfig
        from pathlib import Path
        from fastapi.concurrency import run_in_threadpool
        
        filename = file.filename or "attachment"
        if target_path:
            final_path = target_path
        else:
            final_path = f"{config.attachment_dir.strip('/\\')}/{_safe_filename(Path(filename).name)}"

            
        target_p = Path(final_path)
        config_for_upload = FnsConfig(
            config.base_url,
            config.token,
            config.vault,
            str(target_p.parent)
        )
        
        try:
            saved_path = await run_in_threadpool(
                relay_attachment,
                config_for_upload,
                target_p.name,
                content
            )
            service.record_attachment_task(user_id, filename, "succeeded", saved_path)
            return {"path": saved_path}
        except ClipError as error:
            service.record_attachment_task(
                user_id, filename, "failed", 
                error_message=str(error), 
                error_stage=error.stage
            )
            raise error
        except Exception as error:
            service.record_attachment_task(
                user_id, filename, "failed", 
                error_message="转存任务处理失败", 
                error_stage="worker"
            )
            raise ClipError("worker", "转存任务处理失败") from error

    from pathlib import Path
    static_dir = Path(__file__).parent.parent / "static"
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")


    return app

