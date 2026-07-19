from collections.abc import Callable

from poc.clip import run
from poc.wechat import ClipError


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
