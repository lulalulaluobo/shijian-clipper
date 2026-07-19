from collections.abc import Callable
import json
import time
from urllib.request import Request, urlopen

from backend.app.config import Settings
from backend.app.pocketbase import PocketBaseClient
from backend.app.service import ClipService
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
    return True


def post_fns(url: str, headers: dict[str, str], payload: dict[str, str]) -> dict:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode())


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
