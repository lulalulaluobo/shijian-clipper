import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

from poc.clip import run
from poc.fns import FnsConfig
from poc.wechat import ClipError, fetch_wechat_article


MAX_REQUEST_BYTES = 64 * 1024
INDEX_PATH = Path(__file__).with_name("web") / "index.html"
def parse_fns_config(value: object, target_dir: object) -> FnsConfig:
    if not isinstance(value, dict):
        raise ClipError("validate", "FNS 配置必须是 JSON 对象")
    api = value.get("api")
    token = value.get("apiToken")
    vault = value.get("vault")
    if not all(isinstance(item, str) and item.strip() for item in (api, token, vault)):
        raise ClipError("validate", "FNS 配置缺少 api、apiToken 或 vault")
    if not isinstance(target_dir, str) or not target_dir.strip():
        raise ClipError("validate", "目标目录不能为空")
    return FnsConfig(api.strip(), token.strip(), vault.strip(), target_dir.strip())


def run_payload(
    payload: object,
    fetch: Callable[[str], str],
    post: Callable[[str, dict[str, str], dict[str, str]], dict[str, object]],
) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ClipError("validate", "请求必须是 JSON 对象")
    url = payload.get("url")
    if not isinstance(url, str):
        raise ClipError("validate", "缺少公众号文章链接")
    config = parse_fns_config(payload.get("fns_config"), payload.get("target_dir"))
    return run(url, config, fetch, post)


def _fetch(source_url: str, timeout: int = 30) -> str:
    return fetch_wechat_article(source_url, timeout=timeout, opener=urlopen)


def _post(
    url: str,
    headers: dict[str, str],
    payload: dict[str, str],
    timeout: int = 30,
) -> dict[str, object]:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def make_handler(
    fetch: Callable[[str], str] = _fetch,
    post: Callable[[str, dict[str, str], dict[str, str]], dict[str, object]] = _post,
) -> type[BaseHTTPRequestHandler]:
    class ClipHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path not in {"/", "/index.html"}:
                self._json_response(404, {"stage": "request", "message": "未找到页面"})
                return
            self._file_response()

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/api/clip":
                self._json_response(404, {"stage": "request", "message": "未找到接口"})
                return
            try:
                payload = self._read_json_body()
                result = run_payload(payload, fetch, post)
            except ClipError as error:
                self._json_response(400, {"stage": error.stage, "message": str(error)})
                return
            except Exception:
                self._json_response(500, {"stage": "request", "message": "请求处理失败"})
                return
            self._json_response(200, result)

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

        def _file_response(self) -> None:
            try:
                content = INDEX_PATH.read_bytes()
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
    parser = argparse.ArgumentParser(description="启动微信公众号转存本地调试页")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), make_handler())
    print(f"调试页已启动：http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
