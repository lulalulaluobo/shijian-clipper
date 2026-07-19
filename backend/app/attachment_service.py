import os
import tempfile
from pathlib import Path
from backend.app.fns_attachment import upload_staged_attachment
from poc.fns import FnsConfig, _safe_filename
from poc.wechat import ClipError

RELAY_STAGING_DIR = Path(tempfile.gettempdir()) / "shijian-fns-relay"

def relay_attachment(config: FnsConfig, filename: str, content: bytes) -> str:
    if not filename or not content:
        raise ClipError("validate", "附件文件名或内容不能为空")
    
    # Ensure safe filename
    safe_name = _safe_filename(Path(filename).name)
    target_path = f"{config.target_dir.strip('/\\')}/{safe_name}"
    
    # Create staging dir
    RELAY_STAGING_DIR.mkdir(parents=True, exist_ok=True)
    
    # Save temporarily
    descriptor, raw_path = tempfile.mkstemp(
        prefix="relay-",
        suffix=Path(filename).suffix,
        dir=RELAY_STAGING_DIR
    )
    staged_file = Path(raw_path)
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(content)
        # Upload
        return upload_staged_attachment(config, staged_file, target_path)
    finally:
        # Cleanup fallback (staged_file.unlink is also inside upload_staged_attachment,
        # but we use try...finally to guarantee deletion in case of other errors)
        if staged_file.exists():
            try:
                staged_file.unlink()
            except OSError:
                pass
