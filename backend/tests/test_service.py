import hashlib
from datetime import UTC, datetime

import pytest

from backend.app.errors import ApiError
from backend.app.service import ClipService


class FakePocketBase:
    def __init__(self):
        self.code_hash = hashlib.sha256(b"invite-code").hexdigest()
        self.invites = {"invite-record": {"id": "invite-record", "code_hash": self.code_hash, "used_by": ""}}
        self.users = {}
        self.auth_users = {"user-a": {"id": "user-a", "access_expires_at": "2999-01-01 00:00:00Z"}}
        self.api_tokens = {}
        self._next_id = 1

    def list_records(self, collection, filter_value, per_page=1):
        if collection == "api_tokens":
            results = []
            for rec in self.api_tokens.values():
                match = True
                if "token_hash" in filter_value:
                    # Extract hash from filter
                    h = filter_value.split('"')[1] if '"' in filter_value else ""
                    if rec.get("token_hash") != h:
                        match = False
                if "user" in filter_value and "&&" not in filter_value:
                    pass  # list all for user
                if 'id = "' in filter_value:
                    tid = filter_value.split('id = "')[1].split('"')[0]
                    if rec.get("id") != tid:
                        match = False
                if 'user = "' in filter_value:
                    uid = filter_value.split('user = "')[1].split('"')[0]
                    if rec.get("user") != uid:
                        match = False
                if match:
                    results.append(rec)
            return results
        if collection == "users" and "user-a" in filter_value:
            return [self.auth_users["user-a"]]
        if collection != "invite_codes" or self.code_hash not in filter_value:
            return []
        return [invite for invite in self.invites.values() if not invite["used_by"]]

    def create_user(self, email, password):
        user = {"id": f"user-{len(self.users) + 1}", "email": email}
        self.users[user["id"]] = user
        return user

    def create_record(self, collection, body):
        rec_id = f"rec-{self._next_id}"
        self._next_id += 1
        record = {"id": rec_id, "created": "2026-07-20T10:00:00Z", **body}
        if collection == "api_tokens":
            self.api_tokens[rec_id] = record
        return record

    def update_record(self, collection, record_id, body):
        (self.users if collection == "users" else self.invites)[record_id].update(body)

    def delete_record(self, collection, record_id):
        if collection == "api_tokens":
            self.api_tokens.pop(record_id, None)
        else:
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


def test_current_user_accepts_api_token():
    """sk_ prefixed API Tokens should authenticate via the api_tokens table."""
    pb = FakePocketBase()
    service = ClipService(pb)

    # Generate token, then authenticate with it
    result = service.generate_api_token("user-a", "test")
    raw_token = result["token"]
    assert raw_token.startswith("sk_")

    user_id = service.current_user(raw_token)
    assert user_id == "user-a"


def test_current_user_rejects_invalid_api_token():
    service = ClipService(FakePocketBase())
    with pytest.raises(ApiError, match="API Token 无效"):
        service.current_user("sk_not_a_real_token")


def test_generate_api_token_returns_once_and_stores_hash():
    pb = FakePocketBase()
    service = ClipService(pb)

    result = service.generate_api_token("user-a", "MacBook")
    assert result["token"].startswith("sk_")
    assert result["label"] == "MacBook"

    # Verify the hash was stored, not the raw token
    stored = list(pb.api_tokens.values())[0]
    assert "token_hash" in stored
    assert stored["token_hash"] == hashlib.sha256(result["token"].encode()).hexdigest()


def test_list_api_tokens_returns_metadata_only():
    pb = FakePocketBase()
    service = ClipService(pb)

    service.generate_api_token("user-a", "iPhone")
    tokens = service.list_api_tokens("user-a")
    assert len(tokens) == 1
    assert tokens[0]["label"] == "iPhone"
    assert "token_hash" not in tokens[0]


def test_delete_api_token_removes_record():
    pb = FakePocketBase()
    service = ClipService(pb)

    result = service.generate_api_token("user-a", "temp")
    token_id = result["id"]

    service.delete_api_token("user-a", token_id)
    assert len(pb.api_tokens) == 0


def test_delete_api_token_rejects_wrong_owner():
    pb = FakePocketBase()
    service = ClipService(pb)

    service.generate_api_token("user-a", "mine")
    with pytest.raises(ApiError, match="Token 不存在"):
        service.delete_api_token("user-b", list(pb.api_tokens.values())[0]["id"])


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


# ---------- 新增：notes 同步相关测试 ----------


class NotesPocketBase:
    """支持 notes collection 的 fake，记录 create/update/list_sorted 调用。"""

    def __init__(self, notes=None):
        self.notes = notes or []
        self.created = []
        self.updated = []

    def create_record(self, collection, body):
        record = {"id": f"note-{len(self.created) + 1}", "created": "2026-07-19T10:00:00Z", **body}
        self.created.append((collection, body))
        if collection == "notes":
            self.notes.append(record)
        return record

    def update_record(self, collection, record_id, body):
        self.updated.append((collection, record_id, body))
        for note in self.notes:
            if note["id"] == record_id:
                note.update(body)
                return note
        return {"id": record_id, **body}

    def list_records_sorted(self, collection, filter_value, sort="created", per_page=50):
        # 简单过滤：只返回 delivered=0 的 notes
        return [n for n in self.notes if not n.get("delivered", 0)][:per_page]

    def list_records(self, collection, filter_value, per_page=1):
        # 支持按 id 查询单条 note（用于 _find_user_note）
        if collection != "notes":
            return []
        # 简单解析 filter 里的 id 条件
        if "id = " in filter_value:
            for note in self.notes:
                if note["id"] in filter_value and note.get("user") in filter_value:
                    return [note]
        return []


def test_create_note_writes_article_to_notes_collection():
    pocketbase = NotesPocketBase()
    service = ClipService(pocketbase)
    images = ["https://mmbiz.qpic.cn/a.png", "https://mmbiz.qpic.cn/b.png"]

    result = service.create_note(
        "user-a",
        "https://mp.weixin.qq.com/s/example",
        "文章标题",
        "文章标题.md",
        "# 正文",
        images,
    )

    assert len(pocketbase.created) == 1
    collection, body = pocketbase.created[0]
    assert collection == "notes"
    assert body["user"] == "user-a"
    assert body["source_url"] == "https://mp.weixin.qq.com/s/example"
    assert body["title"] == "文章标题"
    assert body["filename"] == "文章标题.md"
    assert body["content_md"] == "# 正文"
    assert body["images"] == images
    assert body["kind"] == "article"
    assert body["delivered"] == 0
    assert "id" in result


def test_create_attachment_note_stores_base64_bytes():
    pocketbase = NotesPocketBase()
    service = ClipService(pocketbase)

    result = service.create_attachment_note("user-a", "report.pdf", "application/pdf", "JVBERi0=")

    collection, body = pocketbase.created[0]
    assert collection == "notes"
    assert body["kind"] == "attachment"
    assert body["filename"] == "report.pdf"
    assert body["attachment_filename"] == "report.pdf"
    assert body["attachment_mime"] == "application/pdf"
    assert body["attachment_b64"] == "JVBERi0="
    assert body["content_md"] == ""
    assert body["delivered"] == 0
    assert "id" in result


def test_list_pending_notes_returns_undelivered_sorted_by_created():
    notes = [
        {"id": "n1", "user": "user-a", "delivered": 0, "created": "2026-07-19T09:00:00Z", "title": "t1"},
        {"id": "n2", "user": "user-a", "delivered": 0, "created": "2026-07-19T10:00:00Z", "title": "t2"},
        {"id": "n3", "user": "user-a", "delivered": 1, "created": "2026-07-19T08:00:00Z", "title": "t3"},
    ]
    pocketbase = NotesPocketBase(notes=notes)
    service = ClipService(pocketbase)

    result = service.list_pending_notes("user-a", "2026-07-19T00:00:00Z", limit=50)

    # 排除已交付的 n3，按 created 升序
    assert [n["id"] for n in result] == ["n1", "n2"]


def test_ack_notes_marks_delivered_and_clears_attachment_bytes():
    notes = [
        {"id": "n1", "user": "user-a", "delivered": 0, "attachment_b64": "JVBERi0=", "created": "2026-07-19T09:00:00Z"},
        {"id": "n2", "user": "user-a", "delivered": 0, "attachment_b64": "", "created": "2026-07-19T10:00:00Z"},
    ]
    pocketbase = NotesPocketBase(notes=notes)
    service = ClipService(pocketbase)

    acked = service.ack_notes("user-a", ["n1", "n2"])

    assert acked == 2
    # 至少调用 update 两次，清空 attachment_b64 并设置 delivered
    n1_update = next(body for collection, rid, body in pocketbase.updated if rid == "n1")
    assert n1_update["delivered"] == 1
    assert n1_update["attachment_b64"] == ""
    assert "delivered_at" in n1_update


def test_ack_notes_is_idempotent_for_already_delivered():
    notes = [{"id": "n1", "user": "user-a", "delivered": 1, "attachment_b64": "", "created": "2026-07-19T09:00:00Z"}]
    pocketbase = NotesPocketBase(notes=notes)
    service = ClipService(pocketbase)

    acked = service.ack_notes("user-a", ["n1"])

    # 已交付的不重复计入
    assert acked == 0


def test_get_note_attachment_returns_record_for_owner():
    notes = [{"id": "n1", "user": "user-a", "attachment_b64": "JVBERi0=", "attachment_mime": "application/pdf", "attachment_filename": "r.pdf", "kind": "attachment"}]
    pocketbase = NotesPocketBase(notes=notes)
    service = ClipService(pocketbase)

    result = service.get_note_for_user("user-a", "n1")
    assert result["attachment_b64"] == "JVBERi0="


def test_get_note_attachment_rejects_other_user():
    notes = [{"id": "n1", "user": "user-a", "attachment_b64": "JVBERi0="}]
    pocketbase = NotesPocketBase(notes=notes)
    service = ClipService(pocketbase)

    with pytest.raises(ApiError, match="不存在"):
        service.get_note_for_user("user-b", "n1")
