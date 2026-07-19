import unittest

from poc.clip import run
from poc.fns import FnsConfig
from poc.wechat import ClipError


class ClipTests(unittest.TestCase):
    def test_returns_title_image_count_and_fns_path(self):
        def fetch(url: str) -> str:
            return (
                '<meta property="og:title" content="测试文章">'
                '<div id="js_content"><p>正文</p>'
                '<img data-src="https://mmbiz.qpic.cn/a.jpg"></div>'
            )

        def post(url: str, headers: dict[str, str], payload: dict[str, str]) -> dict[str, object]:
            return {"status": True, "data": {"path": payload["path"]}}

        result = run(
            "https://mp.weixin.qq.com/s/example",
            FnsConfig("https://fns.example.com", "token", "Main", "Inbox"),
            fetch,
            post,
        )

        self.assertEqual(
            result,
            {"title": "测试文章", "image_count": 1, "path": "Inbox/测试文章.md"},
        )

    def test_maps_network_error_to_fetch_stage(self):
        def fetch(url: str) -> str:
            raise OSError("network unavailable")

        with self.assertRaisesRegex(ClipError, "文章抓取失败") as context:
            run(
                "https://mp.weixin.qq.com/s/example",
                FnsConfig("https://fns.example.com", "token", "Main", "Inbox"),
                fetch,
                lambda *_: {},
            )

        self.assertEqual(context.exception.stage, "fetch")
