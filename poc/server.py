import argparse
import base64
import json
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

from poc.clip import run
from poc.wechat import ClipError, fetch_wechat_article


MAX_REQUEST_BYTES = 64 * 1024
MAX_ATTACHMENT_REQUEST_BYTES = 20 * 1024 * 1024
INDEX_PATH = Path(__file__).with_name("web") / "index.html"
ATTACHMENT_INDEX_PATH = Path(__file__).with_name("web") / "attachment.html"


def run_payload(
    payload: object,
    fetch: Callable[[str], str],
) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ClipError("validate", "请求必须是 JSON 对象")
    url = payload.get("url")
    if not isinstance(url, str) or not url.strip():
        raise ClipError("validate", "缺少公众号文章链接")
    clip_result = run(url, fetch)
    images = clip_result.get("images", []) or []
    return {
        "title": clip_result["title"],
        "author": clip_result["author"],
        "source_url": clip_result["source_url"],
        "markdown": clip_result["markdown"],
        "image_count": len(images),
        "images": images,
    }


def run_attachment_payload(payload: object) -> dict[str, object]:
    """PoC 附件端点：只接收文件、返回 base64 预览，不再上传到任何后端。"""
    if not isinstance(payload, dict):
        raise ClipError("validate", "附件请求无效")
    filename = payload.get("filename")
    content = payload.get("content")
    mime = payload.get("mime")
    if not isinstance(filename, str) or not filename or not isinstance(content, bytes):
        raise ClipError("validate", "缺少附件文件")
    if not isinstance(mime, str) or not mime:
        mime = "application/octet-stream"
    encoded = base64.b64encode(content).decode("ascii")
    return {
        "filename": filename,
        "mime": mime,
        "size": len(content),
        "b64_preview": encoded[:100],
    }


def _fetch(source_url: str, timeout: int = 30) -> str:
    return fetch_wechat_article(source_url, timeout=timeout)


def is_loopback_host(host: str) -> bool:
    return host.strip().lower() in {"127.0.0.1", "::1", "localhost"}


def make_handler(
    fetch: Callable[[str], str] = _fetch,
) -> type[BaseHTTPRequestHandler]:
    class ClipHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path in {"/", "/index.html"}:
                self._file_response(INDEX_PATH)
                return
            if self.path == "/attachment.html":
                self._file_response(ATTACHMENT_INDEX_PATH)
                return
            else:
                self._json_response(404, {"stage": "request", "message": "未找到页面"})
            return

        def do_POST(self) -> None:  # noqa: N802
            if self.path == "/api/clip":
                try:
                    payload = self._read_json_body()
                    result = run_payload(payload, fetch)
                except ClipError as error:
                    self._json_response(400, {"stage": error.stage, "message": str(error)})
                    return
                except Exception:
                    self._json_response(500, {"stage": "request", "message": "请求处理失败"})
                    return
                self._json_response(200, result)
                return
            if self.path == "/api/attachment":
                try:
                    result = run_attachment_payload(self._read_multipart_body())
                except ClipError as error:
                    self._json_response(400, {"stage": error.stage, "message": str(error)})
                    return
                except Exception:
                    self._json_response(500, {"stage": "request", "message": "附件请求处理失败"})
                    return
                self._json_response(200, result)
                return
            else:
                self._json_response(404, {"stage": "request", "message": "未找到接口"})
                return

        def log_message(self, format: str, *args: object) -> None:
            return

        def _read_json_body(self) -> object:
            try:
                size = int(self.headers.get("Content-Length", "0"))
            except ValueError as error:
                raise ClipError("validate", "请求体长度无效") from error
            if size <= 0 or size > MAX_REQUEST_BYTES:
                raise ClipError("validate", "请求体大小无效")
            try:
                return json.loads(self.rfile.read(size))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ClipError("validate", "请求体必须是 JSON") from error

        def _read_multipart_body(self) -> dict[str, object]:
            try:
                size = int(self.headers.get("Content-Length", "0"))
            except ValueError as error:
                raise ClipError("validate", "请求体长度无效") from error
            content_type = self.headers.get("Content-Type", "")
            if size <= 0 or size > MAX_ATTACHMENT_REQUEST_BYTES or not content_type.startswith("multipart/form-data"):
                raise ClipError("validate", "附件请求大小或格式无效")
            message = BytesParser(policy=default).parsebytes(
                f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + self.rfile.read(size)
            )
            if not message.is_multipart():
                raise ClipError("validate", "附件请求格式无效")
            fields: dict[str, object] = {}
            for part in message.iter_parts():
                name = part.get_param("name", header="content-disposition")
                if name == "file":
                    filename = part.get_filename()
                    content = part.get_payload(decode=True)
                    if not isinstance(filename, str) or not isinstance(content, bytes):
                        raise ClipError("validate", "附件文件无效")
                    fields["filename"] = filename
                    fields["content"] = content
                    fields["mime"] = part.get_content_type()
            return fields

        def _file_response(self, file_path: Path) -> None:
            try:
                content = file_path.read_bytes()
            except OSError:
                self._json_response(500, {"stage": "request", "message": "调试页面不可用"})
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def _json_response(self, status: int, body: dict[str, object]) -> None:
            content = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    return ClipHandler


def main() -> None:
    parser = argparse.ArgumentParser(description="启动微信公众号抓取本地调试页")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--allow-network", action="store_true")
    args = parser.parse_args()
    if not args.allow_network and not is_loopback_host(args.host):
        parser.error("调试页默认只能绑定本机；如确需局域网访问，请显式传入 --allow-network")
    server = ThreadingHTTPServer((args.host, args.port), make_handler())
    print(f"调试页已启动：http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
