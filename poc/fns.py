from dataclasses import dataclass
from typing import Callable

from poc.wechat import ClipError


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
    path = f"{target_dir}/{title}.md" if target_dir else f"{title}.md"
    try:
        response = post(
            f"{config.base_url.rstrip('/')}/api/note",
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
