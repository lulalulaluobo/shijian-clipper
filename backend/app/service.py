import hashlib
from datetime import UTC, datetime, timedelta
from threading import Lock

from backend.app.crypto import decrypt_token, encrypt_token
from backend.app.errors import ApiError
from backend.app.fns import check_fns, parse_fns_json
from backend.app.safe_http import request_public_json
from backend.scripts.create_invite import create_invite_code
from poc.fns import FnsConfig
from poc.wechat import ClipError, validate_wechat_url


class ClipService:
    def __init__(self, pocketbase, fns_encryption_key: str | None = None, fns_get=None) -> None:
        self.pocketbase = pocketbase
        self.fns_encryption_key = fns_encryption_key
        self.fns_get = fns_get or self._get_fns_json
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
                    {"used_by": user_id, "used_at": datetime.now(UTC).isoformat()},
                )
            except Exception:
                self.pocketbase.delete_record("users", user_id)
                raise
        return {"id": user_id, "email": user_email}

    def current_user(self, token: str) -> str:
        user_id = self.pocketbase.authenticate_user(token)
        users = self.pocketbase.list_records("users", f'id = "{user_id}"')
        if not users:
            raise ApiError("用户不存在", 401)
        self._require_active_access(users[0])
        return user_id

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

    def save_fns_settings(self, user_id: str, raw_json: str, target_dir: str, attachment_dir: str | None = None) -> dict:
        if not self.fns_encryption_key:
            raise ApiError("FNS 加密未配置", 500)
        if not target_dir.strip():
            raise ApiError("目标目录不能为空", 400)
        actual_attachment_dir = (attachment_dir or "").strip()
        if not actual_attachment_dir:
            actual_attachment_dir = target_dir.strip()
        base_url, token, vault = parse_fns_json(raw_json)
        body = {
            "user": user_id,
            "base_url": base_url,
            "vault": vault,
            "target_dir": target_dir.strip(),
            "attachment_dir": actual_attachment_dir,
            "token_ciphertext": encrypt_token(token, self.fns_encryption_key),
        }
        existing = self.pocketbase.list_records("fns_settings", f'user = "{user_id}"')
        record = self.pocketbase.update_record("fns_settings", existing[0]["id"], body) if existing else self.pocketbase.create_record("fns_settings", body)
        return self._settings_summary(record)

    def get_fns_settings(self, user_id: str) -> dict:
        records = self.pocketbase.list_records("fns_settings", f'user = "{user_id}"')
        if not records:
            return {"configured": False, "token_saved": False}
        return self._settings_summary(records[0])

    def check_fns_settings(self, user_id: str) -> dict:
        config = self.decrypt_fns_config(user_id)
        return check_fns(config.base_url, config.token, config.vault, self.fns_get)

    def create_clip(self, user_id: str, url: str) -> dict:
        source_url = validate_wechat_url(url)
        if not self.pocketbase.list_records("fns_settings", f'user = "{user_id}"'):
            raise ApiError("请先配置 Fast Note Sync", 400)
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

    def decrypt_fns_config(self, user_id: str) -> FnsConfig:
        if not self.fns_encryption_key:
            raise ApiError("FNS 加密未配置", 500)
        records = self.pocketbase.list_records("fns_settings", f'user = "{user_id}"')
        if not records:
            raise ClipError("fns", "请先配置 Fast Note Sync")
        record = records[0]
        return FnsConfig(
            record["base_url"],
            decrypt_token(record["token_ciphertext"], self.fns_encryption_key),
            record["vault"],
            record["target_dir"],
            record.get("attachment_dir") or record["target_dir"],
        )

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
    def _settings_summary(record: dict) -> dict:
        return {
            "configured": True,
            "base_url": record["base_url"],
            "vault": record["vault"],
            "target_dir": record["target_dir"],
            "attachment_dir": record.get("attachment_dir") or record["target_dir"],
            "token_saved": bool(record.get("token_ciphertext")),
        }


    @staticmethod
    def _task_summary(task: dict) -> dict:
        return {
            key: task[key]
            for key in ("id", "source_url", "status", "title", "path", "error_stage", "error_message", "created", "updated")
            if key in task
        }

    @staticmethod
    def _get_fns_json(url: str, headers: dict[str, str]) -> dict:
        return request_public_json(url, method="GET", headers=headers)
