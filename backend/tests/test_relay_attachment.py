import pytest
from pathlib import Path
from backend.app.attachment_service import relay_attachment, RELAY_STAGING_DIR
from poc.fns import FnsConfig
from poc.wechat import ClipError

def test_relay_attachment_success(tmp_path, monkeypatch):
    config = FnsConfig("https://fns.example", "secret", "obsidian", "00_Inbox")
    
    # Mock upload function
    uploaded = {}
    def mock_upload(cfg, staged_file, target_path):
        uploaded["content"] = staged_file.read_bytes()
        uploaded["target_path"] = target_path
        staged_file.unlink() # Simulate upload_staged_attachment unlinking on success
        return target_path
        
    monkeypatch.setattr("backend.app.attachment_service.upload_staged_attachment", mock_upload)
    
    path = relay_attachment(config, "test.pdf", b"pdf-data")
    
    assert path == "00_Inbox/test.pdf"
    assert uploaded["content"] == b"pdf-data"
    assert uploaded["target_path"] == "00_Inbox/test.pdf"

def test_relay_attachment_validation_error():
    config = FnsConfig("https://fns.example", "secret", "obsidian", "00_Inbox")
    with pytest.raises(ClipError, match="附件文件名或内容不能为空"):
        relay_attachment(config, "", b"")
