import os
from dataclasses import dataclass

from cryptography.fernet import Fernet


@dataclass(frozen=True)
class Settings:
    pocketbase_url: str
    pocketbase_admin_email: str
    pocketbase_admin_password: str
    fns_encryption_key: str
    poll_interval_seconds: int

    @classmethod
    def from_env(cls) -> "Settings":
        values = {
            "POCKETBASE_URL": os.getenv("POCKETBASE_URL", "").strip().rstrip("/"),
            "POCKETBASE_ADMIN_EMAIL": os.getenv("POCKETBASE_ADMIN_EMAIL", "").strip(),
            "POCKETBASE_ADMIN_PASSWORD": os.getenv("POCKETBASE_ADMIN_PASSWORD", "").strip(),
            "FNS_ENCRYPTION_KEY": os.getenv("FNS_ENCRYPTION_KEY", "").strip(),
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise ValueError(f"缺少环境变量: {', '.join(missing)}")
        try:
            Fernet(values["FNS_ENCRYPTION_KEY"].encode())
            poll_interval_seconds = int(os.getenv("WORKER_POLL_INTERVAL_SECONDS", "2"))
        except (TypeError, ValueError) as error:
            raise ValueError("环境变量配置无效") from error
        if poll_interval_seconds <= 0:
            raise ValueError("WORKER_POLL_INTERVAL_SECONDS 必须大于 0")
        return cls(
            pocketbase_url=values["POCKETBASE_URL"],
            pocketbase_admin_email=values["POCKETBASE_ADMIN_EMAIL"],
            pocketbase_admin_password=values["POCKETBASE_ADMIN_PASSWORD"],
            fns_encryption_key=values["FNS_ENCRYPTION_KEY"],
            poll_interval_seconds=poll_interval_seconds,
        )
