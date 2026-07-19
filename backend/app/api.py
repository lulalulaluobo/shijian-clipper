from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.app.errors import ApiError
from poc.wechat import ClipError


class ClipRequest(BaseModel):
    url: str


class FnsSettingsRequest(BaseModel):
    config: str
    target_dir: str


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

    @app.get("/v1/settings/fns")
    def get_fns_settings(user_id: str = Depends(require_user)):
        return service.get_fns_settings(user_id)

    @app.put("/v1/settings/fns")
    def save_fns_settings(payload: FnsSettingsRequest, user_id: str = Depends(require_user)):
        return service.save_fns_settings(user_id, payload.config, payload.target_dir)

    @app.post("/v1/clips", status_code=201)
    def create_clip(payload: ClipRequest, user_id: str = Depends(require_user)):
        return service.create_clip(user_id, payload.url)

    return app
