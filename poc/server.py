import argparse
import json
import os
import tempfile
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

from backend.app.fns_attachment import upload_staged_attachment
from backend.app.safe_http import UnsafeUrlError, normalize_https_root_url, request_public_json
from poc.clip import run
from poc.fns import FnsConfig, _safe_filename, write_note
from poc.wechat import ClipError, fetch_wechat_article


MAX_REQUEST_BYTES = 64 * 1024
MAX_ATTACHMENT_REQUEST_BYTES = 20 * 1024 * 1024
INDEX_PATH = Path(__file__).with_name("web") / "index.html"
ATTACHMENT_INDEX_PATH = Path(__file__).with_name("web") / "attachment.html"
ATTACHMENT_STAGING_DIR = Path(tempfile.gettempdir()) / "shijian-fns-h5-poc"
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
    try:
        base_url = normalize_https_root_url(api)
    except UnsafeUrlError as error:
        raise ClipError("validate", "FNS 服务地址必须是 HTTPS 根地址") from error
    return FnsConfig(base_url, token.strip(), vault.strip(), target_dir.strip())


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
    # poc.clip.run 已不再写 FNS；此处保留旧契约，由 server 侧调用 write_note 落库。
    clip_result = run(url, fetch)
    title = clip_result["title"]
    author = clip_result["author"]
    source_url = clip_result["source_url"]
    markdown = clip_result["markdown"]
    note_content = "\n".join(
        [
            "---",
            f"title: {json.dumps(title, ensure_ascii=False)}",
            f"author: {json.dumps(author, ensure_ascii=False)}",
            f"source: {json.dumps(source_url, ensure_ascii=False)}",
            "---",
            "",
            f"# {title}",
            "",
            markdown,
        ]
    )
    path = write_note(config, title, note_content, post)
    return {"title": title, "image_count": len(clip_result["images"]), "path": path}


def run_attachment_payload(
    payload: object,
    upload: Callable[[FnsConfig, Path, str], str] = upload_staged_attachment,
) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ClipError("validate", "附件请求无效")
    raw_config = payload.get("fns_config")
    target_dir = payload.get("target_dir")
    filename = payload.get("filename")
    content = payload.get("content")
    if not isinstance(raw_config, str):
        raise ClipError("validate", "缺少 FNS 配置")
    if not isinstance(filename, str) or not filename or not isinstance(content, bytes):
        raise ClipError("validate", "缺少附件文件")
    try:
        config_value = json.loads(raw_config)
    except json.JSONDecodeError as error:
        raise ClipError("validate", "FNS 配置不是有效 JSON") from error
    config = parse_fns_config(config_value, target_dir)
    target_path = f"{config.target_dir.strip('/\\')}/{_safe_filename(Path(filename).name)}"
    ATTACHMENT_STAGING_DIR.mkdir(parents=True, exist_ok=True)
    descriptor, raw_path = tempfile.mkstemp(prefix="attachment-", suffix=Path(filename).suffix, dir=ATTACHMENT_STAGING_DIR)
    staged_file = Path(raw_path)
    with os.fdopen(descriptor, "wb") as file:
        file.write(content)
    path = upload(config, staged_file, target_path)
    return {"path": path, "staging_cleaned": not staged_file.exists()}


def _fetch(source_url: str, timeout: int = 30) -> str:
    return fetch_wechat_article(source_url, timeout=timeout)


def _post(
    url: str,
    headers: dict[str, str],
    payload: dict[str, str],
    timeout: int = 30,
) -> dict[str, object]:
    return request_public_json(
        url,
        method="POST",
        headers=headers,
        payload=payload,
        timeout=timeout,
        allow_private_addresses=True,
    )


def is_loopback_host(host: str) -> bool:
    return host.strip().lower() in {"127.0.0.1", "::1", "localhost"}


def make_handler(
    fetch: Callable[[str], str] = _fetch,
    post: Callable[[str, dict[str, str], dict[str, str]], dict[str, object]] = _post,
    upload: Callable[[FnsConfig, Path, str], str] = upload_staged_attachment,
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
                    result = run_payload(payload, fetch, post)
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
                    result = run_attachment_payload(self._read_multipart_body(), upload)
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
                elif name in {"fns_config", "target_dir"}:
                    content = part.get_payload(decode=True)
                    try:
                        fields[name] = (content or b"").decode("utf-8")
                    except UnicodeDecodeError as error:
                        raise ClipError("validate", "附件表单编码无效") from error
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
    parser = argparse.ArgumentParser(description="启动微信公众号转存本地调试页")
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
