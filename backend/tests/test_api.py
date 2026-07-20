from fastapi.testclient import TestClient
import pytest

from backend.app.api import create_app
from backend.app.errors import ApiError
from backend.app.rate_limit import RateLimiter
from poc.wechat import ClipError


pytestmark = pytest.mark.filterwarnings("ignore:Using `httpx` with `starlette.testclient`")


class FakeService:
    """覆盖 service 所有公共方法。后续 sync 方法在底部定义。"""

    def register(self, invite_code, email, password):
        assert invite_code == "invite-a"
        return {"id": "user-a", "email": email}

    def login(self, email, password):
        assert email == "a@example.com"
        assert password == "long-password"
        return {"token": "token-a", "user": {"id": "user-a", "email": email}}

    def current_user(self, token):
        if token not in ("token-a", "sk_test_token"):
            raise ApiError("登录已失效", 401)
        return "user-a"

    def generate_api_token(self, user_id, label=""):
        return {"id": "tok-1", "token": "sk_test_generated", "label": label}

    def list_api_tokens(self, user_id):
        return [{"id": "tok-1", "label": "MacBook", "created": "2026-07-20T10:00:00Z"}]

    def delete_api_token(self, user_id, token_id):
        if token_id != "tok-1":
            raise ApiError("Token 不存在", 404)

    def create_clip(self, user_id, url):
        return {"id": "task-a", "status": "queued", "source_url": url, "user": user_id}

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

    def create_attachment_note(self, user_id, filename, mime, b64data):
        return {"id": "note-1", "filename": filename}

    def list_pending_notes(self, user_id, since_iso, limit=50):
        return [
            {
                "id": "note-1",
                "kind": "article",
                "source_url": "https://mp.weixin.qq.com/s/x",
                "title": "标题A",
                "filename": "标题A.md",
                "content_md": "# 正文",
                "images": ["https://mmbiz.qpic.cn/a.png"],
                "attachment_filename": "",
                "attachment_mime": "",
                "created": "2026-07-19T10:00:00Z",
            }
        ]

    def ack_notes(self, user_id, note_ids):
        return len(note_ids)

    def get_note_for_user(self, user_id, note_id):
        if note_id == "note-att":
            return {
                "id": "note-att",
                "kind": "attachment",
                "attachment_b64": "JVBERi0=",
                "attachment_mime": "application/pdf",
                "attachment_filename": "r.pdf",
            }
        raise ApiError("笔记不存在", 404)


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


def test_authorized_user_can_check_and_create_invite():
    client = TestClient(create_app(FakeService()))
    headers = {"Authorization": "Bearer token-a"}

    allowed = client.get("/v1/invites", headers=headers)
    created = client.post("/v1/invites", headers=headers)

    assert allowed.json() == {"can_create": True}
    assert created.status_code == 201
    assert created.json() == {"code": "invite-a"}


def test_unauthenticated_request_is_rejected():
    client = TestClient(create_app(FakeService()))

    response = client.get("/v1/clips")

    assert response.status_code == 401


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


def test_limits_repeated_login_attempts_from_one_client():
    client = TestClient(create_app(FakeService(), RateLimiter()))

    for _ in range(10):
        assert client.post("/v1/auth/login", json={"email": "a@example.com", "password": "long-password"}).status_code == 200

    response = client.post("/v1/auth/login", json={"email": "a@example.com", "password": "long-password"})

    assert response.status_code == 429


def test_pwa_static_mount_success():
    client = TestClient(create_app(FakeService()))
    response = client.get("/")
    assert response.status_code == 200
    assert b"<!doctype html>" in response.content
    assert b"Shijian" in response.content


# ---------- 新增：附件上传与同步接口测试 ----------


def test_clips_files_uploads_attachment_to_notes():
    client = TestClient(create_app(FakeService()))

    response = client.post(
        "/v1/clips/files",
        headers={"Authorization": "Bearer token-a"},
        files={"file": ("report.pdf", b"pdf-content", "application/pdf")},
    )

    assert response.status_code == 201
    assert response.json() == {"id": "note-1", "filename": "report.pdf"}


def test_clips_files_requires_auth():
    client = TestClient(create_app(FakeService()))

    response = client.post(
        "/v1/clips/files",
        files={"file": ("report.pdf", b"x", "application/pdf")},
    )

    assert response.status_code == 401


def test_sync_changes_returns_pending_notes():
    client = TestClient(create_app(FakeService()))

    response = client.get(
        "/v1/sync/changes",
        headers={"Authorization": "Bearer token-a"},
        params={"since": "2026-07-19T00:00:00Z", "limit": 50},
    )

    assert response.status_code == 200
    body = response.json()
    assert "notes" in body
    assert "server_time" in body
    assert len(body["notes"]) == 1
    assert body["notes"][0]["id"] == "note-1"
    assert body["notes"][0]["title"] == "标题A"


def test_sync_changes_requires_auth():
    client = TestClient(create_app(FakeService()))

    response = client.get("/v1/sync/changes")

    assert response.status_code == 401


def test_sync_ack_marks_notes_delivered():
    client = TestClient(create_app(FakeService()))

    response = client.post(
        "/v1/sync/ack",
        headers={"Authorization": "Bearer token-a"},
        json={"note_ids": ["note-1", "note-2"]},
    )

    assert response.status_code == 200
    assert response.json() == {"acked": 2}


def test_sync_ack_requires_auth():
    client = TestClient(create_app(FakeService()))

    response = client.post("/v1/sync/ack", json={"note_ids": ["note-1"]})

    assert response.status_code == 401


def test_sync_attachment_download_returns_bytes():
    client = TestClient(create_app(FakeService()))

    response = client.get(
        "/v1/sync/notes/note-att/attachment",
        headers={"Authorization": "Bearer token-a"},
    )

    assert response.status_code == 200
    assert response.content == b"%PDF-"  # base64.b64decode("JVBERi0=") = PDF 文件头


def test_sync_attachment_download_rejects_other_user_or_missing():
    client = TestClient(create_app(FakeService()))

    # 不存在的 note
    response = client.get(
        "/v1/sync/notes/note-missing/attachment",
        headers={"Authorization": "Bearer token-a"},
    )
    assert response.status_code == 404

    # 未登录
    response = client.get("/v1/sync/notes/note-att/attachment")
    assert response.status_code == 401
