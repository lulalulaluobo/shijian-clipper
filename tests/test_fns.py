import unittest

from poc.fns import FnsConfig, write_note
from poc.wechat import ClipError


class FnsTests(unittest.TestCase):
    def test_sends_expected_payload(self):
        called: dict[str, object] = {}
        config = FnsConfig(
            "https://fns.example.com/",
            "secret-token",
            "Main",
            "00_Inbox/微信公众号",
        )

        def post(url: str, headers: dict[str, str], payload: dict[str, str]) -> dict[str, object]:
            called.update(url=url, headers=headers, payload=payload)
            return {
                "status": True,
                "data": {"path": "00_Inbox/微信公众号/测试文章.md"},
            }

        result = write_note(config, "测试文章", "# 测试文章", post)

        self.assertEqual(result, "00_Inbox/微信公众号/测试文章.md")
        self.assertEqual(called["url"], "https://fns.example.com/api/note")
        self.assertEqual(called["headers"], {"token": "secret-token"})
        self.assertEqual(
            called["payload"],
            {
                "vault": "Main",
                "path": "00_Inbox/微信公众号/测试文章.md",
                "content": "# 测试文章",
            },
        )

    def test_raises_fns_error_for_unsuccessful_response(self):
        config = FnsConfig("https://fns.example.com", "secret-token", "Main", "Inbox")

        with self.assertRaisesRegex(ClipError, "Fast Note Sync 写入失败") as context:
            write_note(config, "测试文章", "正文", lambda *_: {"status": False})

        self.assertEqual(context.exception.stage, "fns")
