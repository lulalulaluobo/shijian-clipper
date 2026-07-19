from dataclasses import dataclass
from typing import Callable

from poc.wechat import ClipError
from backend.app.safe_http import UnsafeUrlError, normalize_https_root_url


@dataclass(frozen=True)
class FnsConfig:
    base_url: str
    token: str
    vault: str
    target_dir: str


def write_note(
    config: FnsConfig,
    title: str,
    content: str,
    post: Callable[[str, dict[str, str], dict[str, str]], dict[str, object]],
) -> str:
    target_dir = config.target_dir.strip("/\\")
    try:
        base_url = normalize_https_root_url(config.base_url)
    except UnsafeUrlError as error:
        raise ClipError("fns", "FNS 服务地址必须是 HTTPS 根地址") from error
    filename = _safe_filename(title)
    path = f"{target_dir}/{filename}.md" if target_dir else f"{filename}.md"
    try:
        response = post(
            f"{base_url}/api/note",
            {"token": config.token},
            {"vault": config.vault, "path": path, "content": content},
        )
    except Exception as error:
        raise ClipError("fns", "Fast Note Sync 写入失败") from error

    data = response.get("data")
    note_path = data.get("path") if isinstance(data, dict) else None
    if not response.get("status") or not isinstance(note_path, str) or not note_path:
        raise ClipError("fns", "Fast Note Sync 写入失败")
    return note_path


def _safe_filename(title: str) -> str:
    value = "".join(" " if char in '\\/:*?\"<>|\x00' or ord(char) < 32 else char for char in title)
    value = " ".join(value.split()).strip(". ")
    return value[:120] or "未命名文章"
