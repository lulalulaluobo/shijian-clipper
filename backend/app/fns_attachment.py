from pathlib import Path, PurePosixPath
from typing import Callable

from backend.app.safe_http import request_public_multipart_file
from poc.fns import FnsConfig
from poc.wechat import ClipError


def upload_staged_attachment(
    config: FnsConfig,
    staged_file: Path,
    target_path: str,
    post: Callable[[str, dict[str, str], dict[str, str], Path], dict] | None = None,
) -> str:
    path = _safe_target_path(target_path)
    if not staged_file.is_file():
        raise ClipError("attachment", "附件暂存文件不存在")
    metadata = staged_file.stat()
    try:
        response = (post or _post_fns_attachment)(
            f"{config.base_url.rstrip('/')}/api/file",
            {"token": config.token},
            {
                "vault": config.vault,
                "path": path,
                "ctime": str(metadata.st_ctime_ns // 1_000_000),
                "mtime": str(metadata.st_mtime_ns // 1_000_000),
            },
            staged_file,
        )
    except Exception as error:
        raise ClipError("fns", "Fast Note Sync 附件写入失败") from error
    data = response.get("data") if isinstance(response, dict) else None
    saved_path = data.get("path") if isinstance(data, dict) else None
    if not response.get("status") or not isinstance(saved_path, str) or not saved_path:
        raise ClipError("fns", "Fast Note Sync 附件写入失败")
    try:
        staged_file.unlink()
    except OSError as error:
        raise ClipError("cleanup", "附件已写入 Fast Note Sync，但暂存清理失败") from error
    return saved_path


def _safe_target_path(value: str) -> str:
    normalized = value.strip().replace("\\", "/")
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or any(part in {".", ".."} for part in path.parts):
        raise ClipError("attachment", "附件路径无效")
    return str(path)


def _post_fns_attachment(url: str, headers: dict[str, str], fields: dict[str, str], file_path: Path) -> dict:
    return request_public_multipart_file(
        url,
        headers=headers,
        fields=fields,
        file_path=file_path,
        allow_private_addresses=True,
    )
