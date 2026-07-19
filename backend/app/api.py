from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.app.errors import ApiError
from poc.wechat import ClipError


class ClipRequest(BaseModel):
    url: str


class FnsSettingsRequest(BaseModel):
    config: str
    target_dir: str


class RegisterRequest(BaseModel):
    invite_code: str = Field(min_length=1)
    email: str = Field(min_length=3)
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)


def create_app(service) -> FastAPI:
    app = FastAPI()

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

    @app.get("/v1/settings/fns")
    def get_fns_settings(user_id: str = Depends(require_user)):
        return service.get_fns_settings(user_id)

    @app.put("/v1/settings/fns")
    def save_fns_settings(payload: FnsSettingsRequest, user_id: str = Depends(require_user)):
        return service.save_fns_settings(user_id, payload.config, payload.target_dir)

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

    return app
