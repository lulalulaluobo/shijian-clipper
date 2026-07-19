import hashlib
from datetime import UTC, datetime

import pytest

from backend.app.service import ApiError, ClipService


class FakePocketBase:
    def __init__(self):
        self.code_hash = hashlib.sha256(b"invite-code").hexdigest()
        self.invites = {"invite-record": {"id": "invite-record", "code_hash": self.code_hash, "used_by": ""}}
        self.users = {}
        self.auth_users = {"user-a": {"id": "user-a", "access_expires_at": "2999-01-01 00:00:00Z"}}

    def list_records(self, collection, filter_value):
        if collection == "users" and "user-a" in filter_value:
            return [self.auth_users["user-a"]]
        if collection != "invite_codes" or self.code_hash not in filter_value:
            return []
        return [invite for invite in self.invites.values() if not invite["used_by"]]

    def create_user(self, email, password):
        user = {"id": f"user-{len(self.users) + 1}", "email": email}
        self.users[user["id"]] = user
        return user

    def update_record(self, collection, record_id, body):
        (self.users if collection == "users" else self.invites)[record_id].update(body)

    def delete_record(self, collection, record_id):
        self.users.pop(record_id, None)

    def authenticate_user(self, token):
        if token != "valid-token":
            raise ApiError("登录已失效", 401)
        return "user-a"

    def login_user(self, email, password):
        if email != "a@example.com" or password != "long-password":
            raise ApiError("邮箱或密码错误", 401)
        return {"token": "session-token", "record": {"id": "user-a", "email": email, "access_expires_at": "2999-01-01 00:00:00Z"}}


def test_register_consumes_matching_invite_once():
    service = ClipService(FakePocketBase())

    created = service.register("invite-code", "a@example.com", "long-password")

    assert created == {"id": "user-1", "email": "a@example.com"}
    with pytest.raises(ApiError, match="邀请码无效或已使用"):
        service.register("invite-code", "b@example.com", "long-password")


def test_current_user_is_taken_only_from_authenticated_token():
    service = ClipService(FakePocketBase())

    assert service.current_user("valid-token") == "user-a"
    with pytest.raises(ApiError, match="登录已失效"):
        service.current_user("forged-user-id")


def test_login_returns_pocketbase_session_without_password():
    service = ClipService(FakePocketBase())

    assert service.login("a@example.com", "long-password") == {
        "token": "session-token",
        "user": {"id": "user-a", "email": "a@example.com"},
    }


def test_create_invite_requires_authorized_user():
    class InvitePocketBase:
        def __init__(self, allowed):
            self.allowed = allowed
            self.created = None

        def list_records(self, collection, filter_value, per_page=1):
            if collection == "users" and "user-a" in filter_value:
                return [{"id": "user-a", "can_create_invites": self.allowed}]
            return []

        def create_record(self, collection, body):
            self.created = (collection, body)
            return body

    denied = ClipService(InvitePocketBase(False))
    with pytest.raises(ApiError, match="没有生成邀请码权限"):
        denied.create_invite("user-a")

    pocketbase = InvitePocketBase(True)
    created = ClipService(pocketbase).create_invite("user-a")

    assert len(created["code"]) >= 24
    assert pocketbase.created == (
        "invite_codes",
        {"code": created["code"], "code_hash": hashlib.sha256(created["code"].encode()).hexdigest()},
    )


def test_register_assigns_thirty_day_access_to_invited_user():
    class RegistrationPocketBase:
        def __init__(self):
            self.invite = {"id": "invite-a", "code_hash": hashlib.sha256(b"invite-code").hexdigest(), "used_by": ""}
            self.updates = []

        def list_records(self, collection, filter_value, per_page=1):
            return [self.invite] if collection == "invite_codes" else []

        def create_user(self, email, password):
            return {"id": "user-a", "email": email}

        def update_record(self, collection, record_id, body):
            self.updates.append((collection, record_id, body))

        def delete_record(self, collection, record_id):
            raise AssertionError("registration should not be rolled back")

    pocketbase = RegistrationPocketBase()
    ClipService(pocketbase).register("invite-code", "a@example.com", "long-password")

    expiry = next(body["access_expires_at"] for collection, _, body in pocketbase.updates if collection == "users")
    assert datetime.fromisoformat(expiry.replace("Z", "+00:00")) > datetime.now(UTC)


def test_current_user_rejects_expired_access():
    class ExpiredPocketBase:
        def authenticate_user(self, token):
            return "user-a"

        def list_records(self, collection, filter_value, per_page=1):
            return [{"id": "user-a", "access_expires_at": "2000-01-01 00:00:00Z"}]

    with pytest.raises(ApiError, match="使用期限已到"):
        ClipService(ExpiredPocketBase()).current_user("valid-token")


def test_list_and_retry_clips_are_scoped_to_authenticated_user():
    class TaskPocketBase:
        task = {
            "id": "task-a",
            "user": "user-a",
            "source_url": "https://mp.weixin.qq.com/s/example",
            "status": "failed",
            "error_message": "抓取失败",
        }

        def list_records(self, collection, filter_value, per_page=1):
            if collection != "clip_tasks" or "user-a" not in filter_value:
                return []
            if "task-a" in filter_value or "id =" not in filter_value:
                return [self.task]
            return []

        def update_record(self, collection, record_id, body):
            assert collection == "clip_tasks"
            assert record_id == "task-a"
            self.task.update(body)
            return self.task

    service = ClipService(TaskPocketBase())

    assert service.list_clips("user-a")["items"][0]["error_message"] == "抓取失败"
    assert service.retry_clip("user-a", "task-a")["status"] == "queued"
    with pytest.raises(ApiError, match="转存任务不存在"):
        service.retry_clip("user-b", "task-a")


def test_record_attachment_task():
    class RecordPocketBase:
        def __init__(self):
            self.created = []

        def create_record(self, collection, body):
            self.created.append((collection, body))
            return body

    pocketbase = RecordPocketBase()
    service = ClipService(pocketbase)
    service.record_attachment_task("user-a", "report.pdf", "succeeded", "00_Inbox/report.pdf")

    assert len(pocketbase.created) == 1
    collection, body = pocketbase.created[0]
    assert collection == "clip_tasks"
    assert body["user"] == "user-a"
    assert body["source_url"] == "https://attachment.local/report.pdf"
    assert body["status"] == "succeeded"
    assert body["title"] == "report.pdf"
    assert body["path"] == "00_Inbox/report.pdf"

