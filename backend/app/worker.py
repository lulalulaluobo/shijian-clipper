from collections.abc import Callable
import time

from backend.app.config import Settings
from backend.app.pocketbase import PocketBaseClient
from backend.app.service import ClipService
from backend.app.safe_http import request_public_json
from poc.clip import run
from poc.wechat import ClipError, fetch_wechat_article


def process_once(service, fetch: Callable, post: Callable, run_clip=run) -> bool:
    task = service.claim_next_task()
    if task is None:
        return False
    try:
        result = run_clip(task["source_url"], service.decrypt_fns_config(task["user"]), fetch, post)
        service.finish_task(task["id"], result)
    except ClipError as error:
        service.fail_task(task["id"], error)
    except Exception:
        service.fail_task(task["id"], ClipError("worker", "转存任务处理失败"))
    return True


def post_fns(url: str, headers: dict[str, str], payload: dict[str, str]) -> dict:
    return request_public_json(url, method="POST", headers=headers, payload=payload)


def main() -> None:
    settings = Settings.from_env()
    service = ClipService(
        PocketBaseClient(settings.pocketbase_url, settings.pocketbase_admin_email, settings.pocketbase_admin_password),
        settings.fns_encryption_key,
    )
    while True:
        if not process_once(service, fetch_wechat_article, post_fns):
            time.sleep(settings.poll_interval_seconds)


if __name__ == "__main__":
    main()
