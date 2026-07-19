import unittest

from poc.clip import run
from poc.wechat import ClipError


class ClipTests(unittest.TestCase):
    def test_returns_markdown_and_images_without_writing_fns(self):
        def fetch(url: str) -> str:
            return (
                '<meta property="og:title" content="测试文章">'
                '<div id="js_name">作者甲</div>'
                '<div id="js_content"><p>正文</p>'
                '<img data-src="https://mmbiz.qpic.cn/a.jpg"></div>'
            )

        result = run("https://mp.weixin.qq.com/s/example", fetch)

        self.assertEqual(
            result,
            {
                "title": "测试文章",
                "author": "作者甲",
                "source_url": "https://mp.weixin.qq.com/s/example",
                "markdown": "正文\n\n![image](https://mmbiz.qpic.cn/a.jpg)",
                "images": ["https://mmbiz.qpic.cn/a.jpg"],
            },
        )

    def test_maps_network_error_to_fetch_stage(self):
        def fetch(url: str) -> str:
            raise OSError("network unavailable")

        with self.assertRaisesRegex(ClipError, "文章抓取失败") as context:
            run("https://mp.weixin.qq.com/s/example", fetch)

        self.assertEqual(context.exception.stage, "fetch")
