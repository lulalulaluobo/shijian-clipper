import hashlib
import json
from datetime import UTC, datetime
from threading import Lock
from urllib.request import Request, urlopen

from backend.app.crypto import decrypt_token, encrypt_token
from backend.app.errors import ApiError
from backend.app.fns import check_fns, parse_fns_json
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
                    "invite_codes",
                    invitations[0]["id"],
                    {"used_by": user_id, "used_at": datetime.now(UTC).isoformat()},
                )
            except Exception:
                self.pocketbase.delete_record("users", user_id)
                raise
        return {"id": user_id, "email": user_email}

    def current_user(self, token: str) -> str:
        return self.pocketbase.authenticate_user(token)

    def login(self, email: str, password: str) -> dict:
        payload = self.pocketbase.login_user(email.strip(), password)
        token = payload.get("token")
        record = payload.get("record")
        user_id = record.get("id") if isinstance(record, dict) else None
        user_email = record.get("email") if isinstance(record, dict) else None
        if not all(isinstance(item, str) and item for item in (token, user_id, user_email)):
            raise ApiError("登录响应无效", 502)
        return {"token": token, "user": {"id": user_id, "email": user_email}}

    def save_fns_settings(self, user_id: str, raw_json: str, target_dir: str) -> dict:
        if not self.fns_encryption_key:
            raise ApiError("FNS 加密未配置", 500)
        if not target_dir.strip():
            raise ApiError("目标目录不能为空", 400)
        base_url, token, vault = parse_fns_json(raw_json)
        body = {
            "user": user_id,
            "base_url": base_url,
            "vault": vault,
            "target_dir": target_dir.strip(),
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

    @staticmethod
    def _settings_summary(record: dict) -> dict:
        return {
            "configured": True,
            "base_url": record["base_url"],
            "vault": record["vault"],
            "target_dir": record["target_dir"],
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
        request = Request(url, headers=headers)
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode())
        if not isinstance(payload, dict):
            raise ValueError("FNS response is not an object")
        return payload
