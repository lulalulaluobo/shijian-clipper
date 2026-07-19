import hashlib
from datetime import UTC, datetime
from threading import Lock

from backend.app.errors import ApiError


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
