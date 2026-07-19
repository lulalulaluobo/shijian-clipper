from fastapi.testclient import TestClient
import pytest

from backend.app.api import create_app
from backend.app.errors import ApiError
from poc.wechat import ClipError


pytestmark = pytest.mark.filterwarnings("ignore:Using `httpx` with `starlette.testclient`")


class FakeService:
    def current_user(self, token):
        if token != "token-a":
            raise ApiError("登录已失效", 401)
        return "user-a"

    def create_clip(self, user_id, url):
        return {"id": "task-a", "status": "queued", "source_url": url, "user": user_id}

    def save_fns_settings(self, user_id, raw_json, target_dir):
        raise ApiError("FNS 配置无效", 400)


def test_create_clip_uses_authenticated_owner():
    client = TestClient(create_app(FakeService()))

    response = client.post(
        "/v1/clips",
        headers={"Authorization": "Bearer token-a"},
        json={"url": "https://mp.weixin.qq.com/s/example"},
    )

    assert response.status_code == 201
    assert response.json()["user"] == "user-a"


def test_invalid_token_and_fns_error_never_echo_token():
    client = TestClient(create_app(FakeService()))
    secret = "secret-token"

    response = client.put("/v1/settings/fns", json={"config": secret, "target_dir": "Inbox"})

    assert response.status_code == 401
    assert secret not in response.text


def test_clip_error_returns_stage_without_stacktrace():
    class InvalidClipService(FakeService):
        def create_clip(self, user_id, url):
            raise ClipError("validate", "仅支持 HTTPS 微信公众号文章链接")

    response = TestClient(create_app(InvalidClipService())).post(
        "/v1/clips",
        headers={"Authorization": "Bearer token-a"},
        json={"url": "https://example.com"},
    )

    assert response.status_code == 400
    assert response.json() == {"stage": "validate", "message": "仅支持 HTTPS 微信公众号文章链接"}
