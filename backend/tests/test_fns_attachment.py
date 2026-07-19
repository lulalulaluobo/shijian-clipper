from pathlib import Path

import pytest

from backend.app.fns_attachment import upload_staged_attachment
from poc.fns import FnsConfig
from poc.wechat import ClipError


def _config() -> FnsConfig:
    return FnsConfig("https://fns.example", "secret", "obsidian", "00_Inbox")


def test_successful_fns_attachment_upload_removes_only_the_staged_copy(tmp_path: Path):
    staged_file = tmp_path / "staged.pdf"
    staged_file.write_bytes(b"pdf-content")
    captured = {}

    def post(url, headers, fields, file_path):
        captured.update(url=url, headers=headers, fields=fields, file_path=file_path)
        assert file_path.read_bytes() == b"pdf-content"
        return {"status": True, "data": {"path": "00_Inbox/附件/report.pdf"}}

    path = upload_staged_attachment(_config(), staged_file, "00_Inbox/附件/report.pdf", post)

    assert path == "00_Inbox/附件/report.pdf"
    assert not staged_file.exists()
    assert captured["url"] == "https://fns.example/api/file"
    assert captured["headers"] == {"token": "secret"}
    assert captured["fields"]["vault"] == "obsidian"
    assert captured["fields"]["path"] == "00_Inbox/附件/report.pdf"
    assert captured["fields"]["ctime"].isdigit()
    assert captured["fields"]["mtime"].isdigit()


def test_failed_fns_attachment_upload_keeps_staged_copy_for_retry(tmp_path: Path):
    staged_file = tmp_path / "staged.xlsx"
    staged_file.write_bytes(b"excel-content")

    def post(*_):
        raise OSError("network unavailable")

    with pytest.raises(ClipError, match="Fast Note Sync 附件写入失败"):
        upload_staged_attachment(_config(), staged_file, "00_Inbox/附件/report.xlsx", post)

    assert staged_file.read_bytes() == b"excel-content"


def test_invalid_fns_attachment_response_keeps_staged_copy(tmp_path: Path):
    staged_file = tmp_path / "staged.png"
    staged_file.write_bytes(b"image-content")

    with pytest.raises(ClipError, match="Fast Note Sync 附件写入失败"):
        upload_staged_attachment(
            _config(),
            staged_file,
            "00_Inbox/附件/image.png",
            lambda *_: {"status": True, "data": {}},
        )

    assert staged_file.exists()


def test_attachment_target_path_cannot_escape_vault(tmp_path: Path):
    staged_file = tmp_path / "staged.txt"
    staged_file.write_text("content")

    with pytest.raises(ClipError, match="附件路径无效"):
        upload_staged_attachment(_config(), staged_file, "../outside.txt", lambda *_: {})

    assert staged_file.exists()
