import argparse
import shutil
import uuid
from pathlib import Path

from backend.app.fns import parse_fns_json
from backend.app.fns_attachment import upload_staged_attachment
from poc.fns import FnsConfig


def run(config_file: Path, source_file: Path, target_path: str, staging_dir: Path) -> str:
    if not source_file.is_file():
        raise ValueError("测试文件不存在")
    base_url, token, vault = parse_fns_json(config_file.read_text())
    staging_dir.mkdir(parents=True, exist_ok=True)
    staged_file = staging_dir / f"{uuid.uuid4().hex}{source_file.suffix}"
    shutil.copyfile(source_file, staged_file)
    staged_file.chmod(0o600)
    return upload_staged_attachment(FnsConfig(base_url, token, vault, ""), staged_file, target_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="验证 FNS 附件上传与 VPS 暂存清理")
    parser.add_argument("--fns-config", required=True, type=Path, help="包含 api、apiToken、vault 的本地 JSON 文件")
    parser.add_argument("--file", required=True, type=Path, help="用于验证的本地文件")
    parser.add_argument("--target-path", required=True, help="写入 FNS Vault 的相对路径")
    parser.add_argument("--staging-dir", type=Path, default=Path("/tmp/shijian-fns-poc"))
    args = parser.parse_args()
    path = run(args.fns_config, args.file, args.target_path, args.staging_dir)
    print(f"FNS 写入成功：{path}")


if __name__ == "__main__":
    main()
