from backend.app.worker import process_once
from poc.wechat import ClipError


class FakeService:
    def __init__(self, error=None):
        self.task = {"id": "task-a", "user": "user-a", "source_url": "https://mp.weixin.qq.com/s/example"}
        self.error = error
        self.finished = None
        self.failed = None

    def claim_next_task(self):
        return self.task

    def decrypt_fns_config(self, user_id):
        return object()

    def finish_task(self, task_id, result):
        self.finished = (task_id, result)

    def fail_task(self, task_id, error):
        self.failed = (task_id, error.stage)


def test_process_once_marks_task_succeeded():
    service = FakeService()

    assert process_once(service, lambda *_: "", lambda *_: {}, run_clip=lambda *_: {"path": "Inbox/标题.md"}) is True
    assert service.finished == ("task-a", {"path": "Inbox/标题.md"})


def test_process_once_maps_clip_error_to_failed_task():
    service = FakeService()

    def fail(*_):
        raise ClipError("fetch", "文章抓取失败")

    assert process_once(service, lambda *_: "", lambda *_: {}, run_clip=fail) is True
    assert service.failed == ("task-a", "fetch")
