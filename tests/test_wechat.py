import unittest

from poc.wechat import ClipError, extract_article, validate_wechat_url


class ValidateWechatUrlTests(unittest.TestCase):
    def test_accepts_https_article_url(self):
        self.assertEqual(
            validate_wechat_url("https://mp.weixin.qq.com/s/example?foo=bar"),
            "https://mp.weixin.qq.com/s/example?foo=bar",
        )

    def test_rejects_non_wechat_or_non_https_url(self):
        for url in ("http://mp.weixin.qq.com/s/example", "https://example.com/s/example"):
            with self.assertRaisesRegex(ClipError, "仅支持 HTTPS 微信公众号文章链接") as context:
                validate_wechat_url(url)
            self.assertEqual(context.exception.stage, "validate")


class ExtractArticleTests(unittest.TestCase):
    def test_reads_title_author_and_js_content(self):
        source_html = '''
        <meta property="og:title" content="测试文章">
        <span id="js_name">测试作者</span>
        <div id="js_content"><p>第一段</p><p><strong>重点</strong></p></div>
        '''

        article = extract_article(source_html, "https://mp.weixin.qq.com/s/example")

        self.assertEqual(article.title, "测试文章")
        self.assertEqual(article.author, "测试作者")
        self.assertEqual(article.content_html, "<p>第一段</p><p><strong>重点</strong></p>")
