from fastapi.testclient import TestClient
import pytest

from backend.app.api import create_app
from backend.app.errors import ApiError
from poc.wechat import ClipError


pytestmark = pytest.mark.filterwarnings("ignore:Using `httpx` with `starlette.testclient`")


class FakeService:
    def register(self, invite_code, email, password):
        assert invite_code == "invite-a"
        return {"id": "user-a", "email": email}

    def login(self, email, password):
        assert email == "a@example.com"
        assert password == "long-password"
        return {"token": "token-a", "user": {"id": "user-a", "email": email}}

    def current_user(self, token):
        if token != "token-a":
            raise ApiError("登录已失效", 401)
        return "user-a"

    def create_clip(self, user_id, url):
        return {"id": "task-a", "status": "queued", "source_url": url, "user": user_id}

    def save_fns_settings(self, user_id, raw_json, target_dir):
        raise ApiError("FNS 配置无效", 400)

    def check_fns_settings(self, user_id):
        return {"connected": True, "vault_exists": True}

    def can_create_invites(self, user_id):
        assert user_id == "user-a"
        return True

    def create_invite(self, user_id):
        assert user_id == "user-a"
        return {"code": "invite-a"}

    def list_clips(self, user_id):
        return {"items": [{"id": "task-a", "user": user_id, "status": "queued"}]}

    def retry_clip(self, user_id, task_id):
        return {"id": task_id, "status": "queued", "user": user_id}


def test_create_clip_uses_authenticated_owner():
    client = TestClient(create_app(FakeService()))

    response = client.post(
        "/v1/clips",
        headers={"Authorization": "Bearer token-a"},
        json={"url": "https://mp.weixin.qq.com/s/example"},
    )

    assert response.status_code == 201
    assert response.json()["user"] == "user-a"


def test_register_then_login_returns_only_session_and_public_user_fields():
    client = TestClient(create_app(FakeService()))

    registered = client.post(
        "/v1/auth/register",
        json={"invite_code": "invite-a", "email": "a@example.com", "password": "long-password"},
    )
    logged_in = client.post("/v1/auth/login", json={"email": "a@example.com", "password": "long-password"})

    assert registered.status_code == 201
    assert registered.json() == {"id": "user-a", "email": "a@example.com"}
    assert logged_in.json() == {"token": "token-a", "user": {"id": "user-a", "email": "a@example.com"}}


def test_authenticated_settings_check_and_task_list():
    client = TestClient(create_app(FakeService()))
    headers = {"Authorization": "Bearer token-a"}

    checked = client.post("/v1/settings/fns/check", headers=headers)
    clips = client.get("/v1/clips", headers=headers)
    retried = client.post("/v1/clips/task-a/retry", headers=headers)

    assert checked.json() == {"connected": True, "vault_exists": True}
    assert clips.json()["items"][0]["user"] == "user-a"
    assert retried.json()["status"] == "queued"


def test_authorized_user_can_check_and_create_invite():
    client = TestClient(create_app(FakeService()))
    headers = {"Authorization": "Bearer token-a"}

    allowed = client.get("/v1/invites", headers=headers)
    created = client.post("/v1/invites", headers=headers)

    assert allowed.json() == {"can_create": True}
    assert created.status_code == 201
    assert created.json() == {"code": "invite-a"}


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
