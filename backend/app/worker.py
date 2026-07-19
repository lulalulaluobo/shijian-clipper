from collections.abc import Callable
import time

from backend.app.config import Settings
from backend.app.pocketbase import PocketBaseClient
from backend.app.service import ClipService
from poc.clip import run
from poc.wechat import ClipError, _safe_filename, fetch_wechat_article


def process_once(service, fetch: Callable, run_clip: Callable = run) -> bool:
    """取一条 queued 任务，抓取文章并落 notes 表。成功返回 True，无任务返回 False。"""
    task = service.claim_next_task()
    if task is None:
        return False
    try:
        result = run_clip(task["source_url"], fetch)
        service.create_note(
            task["user"],
            result["source_url"],
            result["title"],
            f"{_safe_filename(result['title'])}.md",
            result["markdown"],
            result["images"],
            kind="article",
        )
        service.finish_task(task["id"], {"title": result["title"], "path": "待 Obsidian 插件同步"})
    except ClipError as error:
        service.fail_task(task["id"], error)
    except Exception:
        service.fail_task(task["id"], ClipError("worker", "转存任务处理失败"))
    return True


def main() -> None:
    settings = Settings.from_env()
    service = ClipService(
        PocketBaseClient(settings.pocketbase_url, settings.pocketbase_admin_email, settings.pocketbase_admin_password),
    )
    while True:
        if not process_once(service, fetch_wechat_article):
            time.sleep(settings.poll_interval_seconds)


if __name__ == "__main__":
    main()
