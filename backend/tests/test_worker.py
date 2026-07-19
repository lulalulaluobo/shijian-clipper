from backend.app.worker import process_once
from poc.wechat import ClipError


class FakeService:
    def __init__(self, error=None):
        self.task = {"id": "task-a", "user": "user-a", "source_url": "https://mp.weixin.qq.com/s/example"}
        self.error = error
        self.finished = None
        self.failed = None
        self.created_note = None

    def claim_next_task(self):
        return self.task

    def create_note(self, user_id, source_url, title, filename, content_md, images, kind="article"):
        self.created_note = {
            "user": user_id,
            "source_url": source_url,
            "title": title,
            "filename": filename,
            "content_md": content_md,
            "images": images,
            "kind": kind,
        }
        return {"id": "note-1"}

    def finish_task(self, task_id, result):
        self.finished = (task_id, result)

    def fail_task(self, task_id, error):
        self.failed = (task_id, error.stage, str(error))


def test_process_once_creates_note_and_finishes_task():
    service = FakeService()

    def fake_run(url, fetch):
        return {
            "title": "测试文章",
            "author": "作者",
            "source_url": url,
            "markdown": "# 正文",
            "images": ["https://mmbiz.qpic.cn/a.png"],
        }

    assert process_once(service, lambda *_: "", run_clip=fake_run) is True

    # 验证：调用了 create_note 落 notes 表
    assert service.created_note is not None
    assert service.created_note["user"] == "user-a"
    assert service.created_note["source_url"] == "https://mp.weixin.qq.com/s/example"
    assert service.created_note["title"] == "测试文章"
    assert service.created_note["filename"] == "测试文章.md"
    assert service.created_note["content_md"] == "# 正文"
    assert service.created_note["images"] == ["https://mmbiz.qpic.cn/a.png"]
    assert service.created_note["kind"] == "article"
    # 验证：clip_tasks 也被标 succeeded（path 标注待同步）
    assert service.finished == ("task-a", {"title": "测试文章", "path": "待 Obsidian 插件同步"})


def test_process_once_maps_clip_error_to_failed_task():
    service = FakeService()

    def fail(url, fetch):
        raise ClipError("fetch", "文章抓取失败")

    assert process_once(service, lambda *_: "", run_clip=fail) is True
    assert service.failed == ("task-a", "fetch", "文章抓取失败")
    # 失败路径不应落 notes
    assert service.created_note is None


def test_process_once_marks_unexpected_errors_without_exposing_details():
    service = FakeService()

    def boom(url, fetch):
        raise RuntimeError("token=secret")

    assert process_once(service, lambda *_: "", run_clip=boom) is True
    assert service.failed == ("task-a", "worker", "转存任务处理失败")
