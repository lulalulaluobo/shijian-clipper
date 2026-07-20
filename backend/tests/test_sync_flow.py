"""
端到端集成测试：模拟从注册到插件同步的完整链路。

不依赖外部 PocketBase / Docker，全部用内存 fake，但通过完整的
FastAPI TestClient 走真实 HTTP 路由，验证 API 契约正确闭合。

链路：
1. 注册（消费邀请码）→ 登录拿 token
2. POST /v1/clips 创建抓取任务
3. 模拟 worker 调 service.create_note 落 notes 表
4. GET /v1/sync/changes 拉取 → 看到刚落的 note
5. POST /v1/sync/ack 确认 → delivered=true
6. GET /v1/sync/changes 再拉 → 看不到了
7. POST /v1/clips/files 上传附件 → 落 notes 表（kind=attachment）
8. GET /v1/sync/notes/{id}/attachment 下载附件字节
"""
from datetime import UTC, datetime, timedelta
from pathlib import Path
import hashlib

from fastapi.testclient import TestClient
import pytest

from backend.app.api import create_app
from backend.app.errors import ApiError
from poc.wechat import ClipError


pytestmark = pytest.mark.filterwarnings("ignore:Using `httpx` with `starlette.testclient`")


class E2EFakePocketBase:
    """内存版 PocketBase，覆盖 service 用到的所有方法。"""

    def __init__(self):
        self.invite_codes = {}
        self.users = {}
        self.fns_settings = []  # 已废弃，保留空列表兼容
        self.clip_tasks = {}
        self.notes = {}
        self._note_counter = 0
        self._task_counter = 0
        self._user_counter = 0

        # 预置一个邀请码
        code = "E2E-INVITE-CODE"
        self.invite_codes[hashlib.sha256(code.encode()).hexdigest()] = {
            "id": "invite-1",
            "code": code,
            "code_hash": hashlib.sha256(code.encode()).hexdigest(),
            "used_by": "",
        }

    def list_records(self, collection, filter_value, per_page=1):
        if collection == "invite_codes":
            # register 时找未使用的
            return [iv for iv in self.invite_codes.values() if not iv["used_by"]]
        if collection == "users":
            return [u for u in self.users.values() if u["id"] in filter_value]
        if collection == "clip_tasks":
            if "status" in filter_value:
                return [t for t in self.clip_tasks.values() if t["status"] in filter_value]
            return [t for t in self.clip_tasks.values() if t["user"] in filter_value]
        if collection == "fns_settings":
            return []
        if collection == "notes":
            # 用于 _find_user_note（按 id + user）
            if "id = " in filter_value:
                for n in self.notes.values():
                    if n["id"] in filter_value and n["user"] in filter_value:
                        return [n]
            return []
        return []

    def list_records_sorted(self, collection, filter_value, sort="created", per_page=50, page=1):
        # list_pending_notes 用：按 user + delivered 过滤，按 created 升序
        # 简单解析 filter 里的 user 条件
        result = [n for n in self.notes.values() if not n.get("delivered")]
        if 'user = "' in filter_value:
            # 提取 user id
            import re
            m = re.search(r'user = "([^"]+)"', filter_value)
            if m:
                result = [n for n in result if n.get("user") == m.group(1)]
        start = (page - 1) * per_page
        return sorted(result, key=lambda x: x.get("id", ""))[start : start + per_page]

    def create_user(self, email, password):
        self._user_counter += 1
        user = {"id": f"user-{self._user_counter}", "email": email}
        self.users[user["id"]] = user
        return user

    def update_record(self, collection, record_id, body):
        if collection == "users" and record_id in self.users:
            self.users[record_id].update(body)
            return self.users[record_id]
        if collection == "invite_codes":
            for iv in self.invite_codes.values():
                if iv["id"] == record_id:
                    iv.update(body)
                    return iv
        if collection == "clip_tasks" and record_id in self.clip_tasks:
            self.clip_tasks[record_id].update(body)
            return self.clip_tasks[record_id]
        if collection == "notes" and record_id in self.notes:
            self.notes[record_id].update(body)
            return self.notes[record_id]
        return {"id": record_id, **body}

    def delete_record(self, collection, record_id):
        self.users.pop(record_id, None)

    def authenticate_user(self, token):
        # 简单映射：token 就是 user id
        if token not in {u["id"] for u in self.users.values()}:
            raise ApiError("登录已失效", 401)
        return token

    def login_user(self, email, password):
        for u in self.users.values():
            if u["email"] == email:
                return {
                    "token": u["id"],  # 用 user id 当 token，便于 authenticate_user 校验
                    "record": {**u, "access_expires_at": (datetime.now(UTC) + timedelta(days=30)).isoformat().replace("+00:00", "Z")},
                }
        raise ApiError("邮箱或密码错误", 401)

    def create_record(self, collection, body):
        if collection == "invite_codes":
            iv = {"id": f"invite-{len(self.invite_codes) + 1}", **body}
            self.invite_codes[body.get("code_hash", str(len(self.invite_codes)))] = iv
            return iv
        if collection == "clip_tasks":
            self._task_counter += 1
            tid = f"task-{self._task_counter}"
            self.clip_tasks[tid] = {"id": tid, "created": datetime.now(UTC).isoformat(), **body}
            return self.clip_tasks[tid]
        if collection == "notes":
            self._note_counter += 1
            nid = f"note-{self._note_counter}"
            self.notes[nid] = {
                "id": nid,
                "created": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "attachment_b64": "",
                "attachment_mime": "",
                "attachment_filename": "",
                "delivered": 0,
                **body,
            }
            return self.notes[nid]
        return body


@pytest.fixture
def client_and_service():
    from backend.app.service import ClipService
    pocketbase = E2EFakePocketBase()
    service = ClipService(pocketbase)
    client = TestClient(create_app(service))
    return client, service


def test_end_to_end_sync_flow(client_and_service):
    client, service = client_and_service

    # 1. 注册（邀请码已在 fake 预置）
    reg = client.post("/v1/auth/register", json={
        "invite_code": "E2E-INVITE-CODE",
        "email": "user@example.com",
        "password": "long-password",
    })
    assert reg.status_code == 201
    user_id = reg.json()["id"]

    # 2. 登录拿 token（fake 把 user id 当 token）
    login = client.post("/v1/auth/login", json={
        "email": "user@example.com",
        "password": "long-password",
    })
    assert login.status_code == 200
    token = login.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 3. 创建抓取任务
    clip = client.post("/v1/clips", headers=headers, json={
        "url": "https://mp.weixin.qq.com/s/example",
    })
    assert clip.status_code == 201

    # 4. 模拟 worker 抓取成功，落 notes 表
    note = service.create_note(
        user_id,
        "https://mp.weixin.qq.com/s/example",
        "微信公众号测试文章",
        "微信公众号测试文章.md",
        "# 这是正文\n\n一段文字。",
        ["https://mmbiz.qpic.cn/test.png"],
        kind="article",
    )
    note_id = note["id"]

    # 5. 插件拉取 /v1/sync/changes
    changes = client.get("/v1/sync/changes", headers=headers, params={"since": "1970-01-01T00:00:00Z"})
    assert changes.status_code == 200
    body = changes.json()
    assert "notes" in body
    assert "server_time" in body
    assert len(body["notes"]) == 1
    pulled = body["notes"][0]
    assert pulled["id"] == note_id
    assert pulled["title"] == "微信公众号测试文章"
    assert pulled["filename"] == "微信公众号测试文章.md"
    assert pulled["kind"] == "article"
    assert pulled["images"] == ["https://mmbiz.qpic.cn/test.png"]
    assert "content_md" in pulled and "# 这是正文" in pulled["content_md"]
    # attachment_b64 不应在 changes 响应里
    assert "attachment_b64" not in pulled

    # 6. ack 确认
    ack = client.post("/v1/sync/ack", headers=headers, json={"note_ids": [note_id]})
    assert ack.status_code == 200
    assert ack.json() == {"acked": 1}

    # 7. 再拉，应该空了
    changes2 = client.get("/v1/sync/changes", headers=headers, params={"since": "1970-01-01T00:00:00Z"})
    assert changes2.status_code == 200
    assert changes2.json()["notes"] == []

    # 8. 上传附件 → 落 notes 表（kind=attachment）
    upload = client.post(
        "/v1/clips/files",
        headers=headers,
        files={"file": ("report.pdf", b"%PDF-1.4 test content", "application/pdf")},
    )
    assert upload.status_code == 201
    uploaded = upload.json()
    assert "id" in uploaded
    assert uploaded["filename"] == "report.pdf"
    att_note_id = uploaded["id"]

    # 9. 拉取附件 note
    changes3 = client.get("/v1/sync/changes", headers=headers, params={"since": "1970-01-01T00:00:00Z"})
    att_notes = [n for n in changes3.json()["notes"] if n["id"] == att_note_id]
    assert len(att_notes) == 1
    assert att_notes[0]["kind"] == "attachment"
    assert att_notes[0]["attachment_filename"] == "report.pdf"
    assert att_notes[0]["attachment_mime"] == "application/pdf"

    # 10. 下载附件字节
    dl = client.get(f"/v1/sync/notes/{att_note_id}/attachment", headers=headers)
    assert dl.status_code == 200
    assert dl.content == b"%PDF-1.4 test content"
    assert dl.headers["content-type"] == "application/pdf"

    # 11. ack 附件，再下载应该 404（字节已清空）
    client.post("/v1/sync/ack", headers=headers, json={"note_ids": [att_note_id]})
    dl2 = client.get(f"/v1/sync/notes/{att_note_id}/attachment", headers=headers)
    assert dl2.status_code == 404


def test_sync_flow_rejects_other_user_notes(client_and_service):
    """属主隔离：用户 A 的 note 不能被用户 B 拉取或下载。"""
    client, service = client_and_service

    # 注册两个用户
    client.post("/v1/auth/register", json={
        "invite_code": "E2E-INVITE-CODE",
        "email": "a@example.com",
        "password": "long-password",
    })
    # 第二个用户需要一个新邀请码
    from backend.scripts.create_invite import create_invite_code
    code_b = create_invite_code()
    service.pocketbase.invite_codes[hashlib.sha256(code_b.encode()).hexdigest()] = {
        "id": "invite-2",
        "code": code_b,
        "code_hash": hashlib.sha256(code_b.encode()).hexdigest(),
        "used_by": "",
    }
    client.post("/v1/auth/register", json={
        "invite_code": code_b,
        "email": "b@example.com",
        "password": "long-password",
    })

    login_a = client.post("/v1/auth/login", json={"email": "a@example.com", "password": "long-password"}).json()
    login_b = client.post("/v1/auth/login", json={"email": "b@example.com", "password": "long-password"}).json()
    token_a = login_a["token"]
    token_b = login_b["token"]
    user_a_id = login_a["user"]["id"]

    # A 上传一个附件
    upload_a = client.post(
        "/v1/clips/files",
        headers={"Authorization": f"Bearer {token_a}"},
        files={"file": ("secret.pdf", b"A's secret", "application/pdf")},
    )
    note_a_id = upload_a.json()["id"]

    # B 拉取 changes，不应该看到 A 的 note
    changes_b = client.get(
        "/v1/sync/changes",
        headers={"Authorization": f"Bearer {token_b}"},
        params={"since": "1970-01-01T00:00:00Z"},
    )
    assert changes_b.status_code == 200
    assert all(n["id"] != note_a_id for n in changes_b.json()["notes"])

    # B 尝试下载 A 的附件 → 404
    dl = client.get(f"/v1/sync/notes/{note_a_id}/attachment", headers={"Authorization": f"Bearer {token_b}"})
    assert dl.status_code == 404
