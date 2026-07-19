import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from poc.server import _fetch, is_loopback_host, make_handler, run_payload
from poc.wechat import ClipError


class ServerPayloadTests(unittest.TestCase):
    def test_run_payload_returns_markdown_and_images(self):
        payload = {"url": "https://mp.weixin.qq.com/s/example"}

        def fetch(url: str) -> str:
            return (
                '<meta property="og:title" content="测试文章">'
                '<div id="js_content"><p>正文</p></div>'
            )

        result = run_payload(payload, fetch)

        self.assertEqual(result["title"], "测试文章")
        self.assertIn("正文", result["markdown"])
        self.assertEqual(result["source_url"], "https://mp.weixin.qq.com/s/example")
        self.assertEqual(result["image_count"], 0)
        self.assertEqual(result["images"], [])
        # 没有任何 FNS path 字段
        self.assertNotIn("path", result)

    def test_run_payload_requires_url(self):
        with self.assertRaises(ClipError) as context:
            run_payload({}, lambda _: "")

        self.assertEqual(context.exception.stage, "validate")


class LocalHttpServerTests(unittest.TestCase):
    def setUp(self):
        def fetch(url: str) -> str:
            return '<meta property="og:title" content="测试文章"><div id="js_content"><p>正文</p></div>'

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(fetch))
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def _request(self, method: str, path: str, body: bytes | None = None, headers: dict[str, str] | None = None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        connection.request(method, path, body, headers or {"Content-Type": "application/json"})
        response = connection.getresponse()
        content = response.read()
        connection.close()
        return response.status, content

    def test_serves_debug_page(self):
        status, content = self._request("GET", "/")

        self.assertEqual(status, 200)
        self.assertIn(b'id="clip-form"', content)

    def test_api_clip_returns_markdown_and_images(self):
        body = json.dumps(
            {"url": "https://mp.weixin.qq.com/s/example"}
        ).encode("utf-8")

        status, content = self._request("POST", "/api/clip", body)

        self.assertEqual(status, 200)
        payload = json.loads(content)
        self.assertEqual(payload["title"], "测试文章")
        self.assertIn("正文", payload["markdown"])
        self.assertEqual(payload["source_url"], "https://mp.weixin.qq.com/s/example")
        self.assertEqual(payload["image_count"], 0)
        self.assertEqual(payload["images"], [])
        self.assertNotIn("path", payload)

    def test_api_clip_returns_validate_error_for_missing_url(self):
        body = json.dumps({}).encode("utf-8")

        status, content = self._request("POST", "/api/clip", body)

        self.assertEqual(status, 400)
        self.assertEqual(json.loads(content)["stage"], "validate")

    def test_attachment_page_is_served(self):
        status, content = self._request("GET", "/attachment.html")

        self.assertEqual(status, 200)
        self.assertIn(b'id="attachment-form"', content)

    def test_attachment_endpoint_returns_base64_preview(self):
        boundary = "----ShijianTest"
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"report.pdf\"\r\n"
            "Content-Type: application/pdf\r\n\r\n"
        ).encode() + b"pdf-content" + f"\r\n--{boundary}--\r\n".encode()

        status, content = self._request(
            "POST",
            "/api/attachment",
            body,
            {"Content-Type": f"multipart/form-data; boundary={boundary}", "Content-Length": str(len(body))},
        )

        self.assertEqual(status, 200)
        payload = json.loads(content)
        self.assertEqual(payload["filename"], "report.pdf")
        self.assertEqual(payload["mime"], "application/pdf")
        self.assertEqual(payload["size"], len(b"pdf-content"))
        self.assertIn("b64_preview", payload)
        # base64 preview is a prefix of the full base64-encoded content
        import base64
        full_b64 = base64.b64encode(b"pdf-content").decode("ascii")
        self.assertTrue(full_b64.startswith(payload["b64_preview"]))
        # no FNS upload fields
        self.assertNotIn("path", payload)
        self.assertNotIn("staging_cleaned", payload)


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
