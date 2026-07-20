import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from threading import Lock

from backend.app.errors import ApiError
from backend.scripts.create_invite import create_invite_code
from poc.wechat import ClipError, validate_wechat_url


class ClipService:
    def __init__(self, pocketbase) -> None:
        self.pocketbase = pocketbase
        # ponytail: process-local registration lock; use a database transaction before scaling API replicas.
        self._registration_lock = Lock()

    def register(self, invite_code: str, email: str, password: str) -> dict:
        code_hash = hashlib.sha256(invite_code.strip().encode()).hexdigest()
        with self._registration_lock:
            invitations = self.pocketbase.list_records(
                "invite_codes", f'code_hash = "{code_hash}" && used_by = ""'
            )
            if not invitations:
                raise ApiError("邀请码无效或已使用", 400)
            user = self.pocketbase.create_user(email, password)
            user_id = user.get("id")
            user_email = user.get("email")
            if not isinstance(user_id, str) or not isinstance(user_email, str):
                raise ApiError("用户创建失败", 502)
            try:
                self.pocketbase.update_record(
                    "users",
                    user_id,
                    {"access_expires_at": (datetime.now(UTC) + timedelta(days=30)).isoformat().replace("+00:00", "Z")},
                )
                self.pocketbase.update_record(
                    "invite_codes",
                    invitations[0]["id"],
                    {"used_by": user_email, "used_at": datetime.now(UTC).isoformat()},
                )

            except Exception:
                self.pocketbase.delete_record("users", user_id)
                raise
        return {"id": user_id, "email": user_email}

    def current_user(self, token: str) -> str:
        if token.startswith("sk_"):
            return self._authenticate_api_token(token)
        user_id = self.pocketbase.authenticate_user(token)
        users = self.pocketbase.list_records("users", f'id = "{user_id}"')
        if not users:
            raise ApiError("用户不存在", 401)
        self._require_active_access(users[0])
        return user_id

    def _authenticate_api_token(self, token: str) -> str:
        """通过 sk_ 前缀的 API Token 鉴权，返回 user_id。"""
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        records = self.pocketbase.list_records("api_tokens", f'token_hash = "{token_hash}"')
        if not records:
            raise ApiError("API Token 无效", 401)
        user_id = records[0].get("user")
        if not isinstance(user_id, str) or not user_id:
            raise ApiError("API Token 无效", 401)
        users = self.pocketbase.list_records("users", f'id = "{user_id}"')
        if not users:
            raise ApiError("用户不存在", 401)
        self._require_active_access(users[0])
        return user_id

    def generate_api_token(self, user_id: str, label: str = "") -> dict:
        """为用户生成一个 API Token，返回含明文 token 的字典（仅此一次可见）。"""
        raw = f"sk_{secrets.token_hex(32)}"
        token_hash = hashlib.sha256(raw.encode()).hexdigest()
        record = self.pocketbase.create_record(
            "api_tokens", {"user": user_id, "token_hash": token_hash, "label": label.strip()[:128]}
        )
        return {"id": record.get("id"), "token": raw, "label": label.strip()[:128]}

    def list_api_tokens(self, user_id: str) -> list[dict]:
        """列出该用户所有 API Token（不含 hash）。"""
        records = self.pocketbase.list_records("api_tokens", f'user = "{user_id}"', per_page=50)
        return [{"id": r.get("id"), "label": r.get("label", ""), "created": r.get("created", "")} for r in records]

    def delete_api_token(self, user_id: str, token_id: str) -> None:
        """删除指定 API Token（需属主匹配）。"""
        records = self.pocketbase.list_records("api_tokens", f'id = "{token_id}" && user = "{user_id}"')
        if not records:
            raise ApiError("Token 不存在", 404)
        self.pocketbase.delete_record("api_tokens", token_id)

    def login(self, email: str, password: str) -> dict:
        payload = self.pocketbase.login_user(email.strip(), password)
        token = payload.get("token")
        record = payload.get("record")
        user_id = record.get("id") if isinstance(record, dict) else None
        user_email = record.get("email") if isinstance(record, dict) else None
        if not all(isinstance(item, str) and item for item in (token, user_id, user_email)):
            raise ApiError("登录响应无效", 502)
        self._require_active_access(record)
        return {"token": token, "user": {"id": user_id, "email": user_email}}

    def can_create_invites(self, user_id: str) -> bool:
        users = self.pocketbase.list_records("users", f'id = "{user_id}"')
        return bool(users and users[0].get("can_create_invites"))

    def create_invite(self, user_id: str) -> dict:
        if not self.can_create_invites(user_id):
            raise ApiError("没有生成邀请码权限", 403)
        code = create_invite_code()
        self.pocketbase.create_record(
            "invite_codes", {"code": code, "code_hash": hashlib.sha256(code.encode()).hexdigest()}
        )
        return {"code": code}

    def create_clip(self, user_id: str, url: str) -> dict:
        source_url = validate_wechat_url(url)
        task = self.pocketbase.create_record(
            "clip_tasks",
            {"user": user_id, "source_url": source_url, "status": "queued"},
        )
        return {"id": task["id"], "status": "queued", "source_url": source_url}

    def list_clips(self, user_id: str) -> dict:
        tasks = self.pocketbase.list_records("clip_tasks", f'user = "{user_id}"', 50)
        return {"items": [self._task_summary(task) for task in tasks]}

    def retry_clip(self, user_id: str, task_id: str) -> dict:
        tasks = self.pocketbase.list_records("clip_tasks", f'id = "{task_id}" && user = "{user_id}"')
        if not tasks:
            raise ApiError("转存任务不存在", 404)
        task = self.pocketbase.update_record(
            "clip_tasks",
            task_id,
            {"status": "queued", "error_stage": "", "error_message": ""},
        )
        return self._task_summary(task)

    def claim_next_task(self) -> dict | None:
        tasks = self.pocketbase.list_records("clip_tasks", 'status = "queued"')
        if not tasks:
            return None
        task = tasks[0]
        return self.pocketbase.update_record("clip_tasks", task["id"], {"status": "processing"})

    def finish_task(self, task_id: str, result: dict) -> None:
        self.pocketbase.update_record(
            "clip_tasks",
            task_id,
            {"status": "succeeded", "title": result.get("title", ""), "path": result.get("path", "")},
        )

    def fail_task(self, task_id: str, error: ClipError) -> None:
        self.pocketbase.update_record(
            "clip_tasks",
            task_id,
            {"status": "failed", "error_stage": error.stage, "error_message": str(error)},
        )

    def record_attachment_task(
        self,
        user_id: str,
        filename: str,
        status: str,
        path: str = "",
        error_message: str = "",
        error_stage: str = "",
    ) -> dict:
        """记录附件任务到 clip_tasks（保留用于 APK 任务列表显示）。"""
        source_url = f"https://attachment.local/{filename}"
        body = {
            "user": user_id,
            "source_url": source_url,
            "status": status,
            "title": filename,
            "path": path,
            "error_stage": error_stage,
            "error_message": error_message,
        }
        return self.pocketbase.create_record("clip_tasks", body)

    # ---------- notes 同步相关 ----------

    def create_note(
        self,
        user_id: str,
        source_url: str,
        title: str,
        filename: str,
        content_md: str,
        images: list[str],
        kind: str = "article",
    ) -> dict:
        """Worker 抓取文章成功后，把 Markdown 与图片清单落 notes 表，等插件拉取。"""
        body = {
            "user": user_id,
            "source_url": source_url,
            "title": title,
            "filename": filename,
            "content_md": content_md,
            "images": images,
            "kind": kind,
            "delivered": 0,  # PocketBase 0.38 bool 字段 filter 有 bug，用 number 0/1
        }
        return self.pocketbase.create_record("notes", body)

    def create_attachment_note(
        self,
        user_id: str,
        filename: str,
        mime: str,
        b64data: str,
    ) -> dict:
        """用户从客户端直接上传附件时，把文件字节（base64）落 notes 表（kind=attachment）。"""
        body = {
            "user": user_id,
            "source_url": f"https://attachment.local/{filename}",
            "title": filename,
            "filename": filename,
            "content_md": "",
            "images": [],
            "kind": "attachment",
            "attachment_filename": filename,
            "attachment_mime": mime,
            "attachment_b64": b64data,
            "delivered": 0,
        }
        record = self.pocketbase.create_record("notes", body)
        # 同步在 clip_tasks 记一条成功任务，便于 APK 任务列表显示
        self.record_attachment_task(user_id, filename, "succeeded", record.get("filename", filename))
        return {"id": record.get("id"), "filename": filename}

    def list_pending_notes(self, user_id: str, since_cursor: str, limit: int = 50) -> list[dict]:
        """返回该用户 delivered=0（未交付）的 notes，按 id 排序。"""
        filter_value = f'user = "{user_id}" && delivered = 0'
        if since_cursor:
            filter_value += f' && id > "{since_cursor}"'
        records = self.pocketbase.list_records_sorted(
            "notes", filter_value, sort="id", per_page=limit
        )
        return [self._note_summary(record) for record in records]

    def ack_notes(self, user_id: str, note_ids: list[str]) -> int:
        """把指定 notes 标记为已交付（delivered=1），并清空 attachment_b64 释放空间。返回实际 ack 数量。"""
        acked = 0
        now_iso = datetime.now(UTC).isoformat()
        for note_id in note_ids:
            record = self._find_user_note(user_id, note_id)
            if record is None or record.get("delivered") == 1:
                continue
            self.pocketbase.update_record(
                "notes",
                note_id,
                {"delivered": 1, "delivered_at": now_iso, "attachment_b64": ""},
            )
            acked += 1
        return acked

    def get_note_for_user(self, user_id: str, note_id: str) -> dict:
        """读取单条 note（属主校验）。用于附件字节下载端点。"""
        record = self._find_user_note(user_id, note_id)
        if record is None:
            raise ApiError("笔记不存在", 404)
        return record

    def _find_user_note(self, user_id: str, note_id: str) -> dict | None:
        records = self.pocketbase.list_records(
            "notes", f'id = "{note_id}" && user = "{user_id}"'
        )
        return records[0] if records else None

    @staticmethod
    def _require_active_access(user: dict) -> None:
        expires_at = user.get("access_expires_at")
        if not isinstance(expires_at, str) or not expires_at:
            raise ApiError("使用期限已到，请联系管理员续期", 403)
        try:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise ApiError("使用期限已到，请联系管理员续期", 403) from error
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        if expiry <= datetime.now(UTC):
            raise ApiError("使用期限已到，请联系管理员续期", 403)

    @staticmethod
    def _task_summary(task: dict) -> dict:
        return {
            key: task[key]
            for key in ("id", "source_url", "status", "title", "path", "error_stage", "error_message", "created", "updated")
            if key in task
        }

    @staticmethod
    def _note_summary(record: dict) -> dict:
        return {
            key: record.get(key)
            for key in (
                "id",
                "kind",
                "source_url",
                "title",
                "filename",
                "content_md",
                "images",
                "attachment_filename",
                "attachment_mime",
                "created",
            )
        }
