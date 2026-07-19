import unittest

from poc.markdown import html_to_markdown


class HtmlToMarkdownTests(unittest.TestCase):
    def test_keeps_original_image_url(self):
        markdown, images = html_to_markdown(
            '<p>第一段</p><p><strong>重点</strong></p><img data-src="https://mmbiz.qpic.cn/example.jpg">'
        )

        self.assertEqual(
            markdown,
            "第一段\n\n**重点**\n\n![image](https://mmbiz.qpic.cn/example.jpg)",
        )
        self.assertEqual(images, ["https://mmbiz.qpic.cn/example.jpg"])

    def test_handles_basic_structure(self):
        markdown, images = html_to_markdown(
            '<h2>小节</h2><ul><li>一项</li></ul><p><a href="https://example.com">链接</a>与<code>x</code></p>'
        )

        self.assertEqual(markdown, "## 小节\n\n- 一项\n\n[链接](https://example.com)与`x`")
        self.assertEqual(images, [])
