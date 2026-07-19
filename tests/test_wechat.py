import unittest

from poc.wechat import ClipError, validate_wechat_url


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
