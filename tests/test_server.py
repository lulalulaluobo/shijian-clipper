import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from poc.server import _fetch, is_loopback_host, make_handler, run_payload
from poc.wechat import ClipError


class ServerPayloadTests(unittest.TestCase):
    def test_uses_fns_json_fields(self):
        payload = {
            "url": "https://mp.weixin.qq.com/s/example",
            "target_dir": "Inbox",
            "fns_config": {
                "api": "https://fns.example.com",
                "apiToken": "token",
                "vault": "Main",
                "wsApi": "wss://unused.example.com/api/user/sync",
            },
        }

        def fetch(url: str) -> str:
            return (
                '<meta property="og:title" content="测试文章">'
                '<div id="js_content"><p>正文</p></div>'
            )

        def post(url: str, headers: dict[str, str], request: dict[str, str]) -> dict[str, object]:
            self.assertEqual(url, "https://fns.example.com/api/note")
            self.assertEqual(headers, {"token": "token"})
            self.assertEqual(request["vault"], "Main")
            return {"status": True, "data": {"path": request["path"]}}

        result = run_payload(payload, fetch, post)

        self.assertEqual(result, {"title": "测试文章", "image_count": 0, "path": "Inbox/测试文章.md"})

    def test_does_not_echo_fns_token_in_validation_error(self):
        with self.assertRaises(ClipError) as context:
            run_payload(
                {
                    "url": "not-a-url",
                    "target_dir": "Inbox",
                    "fns_config": {"apiToken": "do-not-echo"},
                },
                lambda _: "",
                lambda *_: {},
            )

        self.assertEqual(context.exception.stage, "validate")
        self.assertNotIn("do-not-echo", str(context.exception))


class LocalHttpServerTests(unittest.TestCase):
    def setUp(self):
        def fetch(url: str) -> str:
            return '<meta property="og:title" content="测试文章"><div id="js_content"><p>正文</p></div>'

        def post(url: str, headers: dict[str, str], request: dict[str, str]) -> dict[str, object]:
            return {"status": True, "data": {"path": request["path"]}}

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(fetch, post))
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def _request(self, method: str, path: str, body: bytes | None = None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        connection.request(method, path, body, {"Content-Type": "application/json"})
        response = connection.getresponse()
        content = response.read()
        connection.close()
        return response.status, content

    def test_serves_debug_page(self):
        status, content = self._request("GET", "/")

        self.assertEqual(status, 200)
        self.assertIn(b'id="clip-form"', content)

    def test_api_error_does_not_echo_fns_token(self):
        body = json.dumps(
            {
                "url": "not-a-url",
                "target_dir": "Inbox",
                "fns_config": {
                    "api": "https://fns.example.com",
                    "apiToken": "do-not-echo",
                    "vault": "Main",
                },
            }
        ).encode("utf-8")

        status, content = self._request("POST", "/api/clip", body)

        self.assertEqual(status, 400)
        self.assertEqual(json.loads(content)["stage"], "validate")
        self.assertNotIn(b"do-not-echo", content)


class WechatFetchTests(unittest.TestCase):
    @patch("poc.server.fetch_wechat_article")
    def test_uses_reference_project_browser_headers(self, fetch_wechat_article):
        _fetch("https://mp.weixin.qq.com/s/example")

        fetch_wechat_article.assert_called_once_with("https://mp.weixin.qq.com/s/example", timeout=30)


class LocalBindTests(unittest.TestCase):
    def test_only_accepts_loopback_hosts_without_explicit_network_opt_in(self):
        assert is_loopback_host("127.0.0.1")
        assert is_loopback_host("::1")
        assert not is_loopback_host("0.0.0.0")
