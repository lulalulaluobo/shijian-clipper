import json
from pathlib import Path

from backend.scripts.poc_fns_attachment import run


def test_poc_stages_a_copy_then_returns_fns_path(tmp_path: Path, monkeypatch):
    config_file = tmp_path / "fns.json"
    config_file.write_text(json.dumps({"api": "https://fns.example", "apiToken": "secret", "vault": "obsidian"}))
    source_file = tmp_path / "report.pdf"
    source_file.write_bytes(b"source-content")
    staging_dir = tmp_path / "staging"
    captured = {}

    def upload(config, staged_file, target_path):
        captured.update(config=config, staged_file=staged_file, target_path=target_path)
        assert staged_file.read_bytes() == b"source-content"
        staged_file.unlink()
        return target_path

    monkeypatch.setattr("backend.scripts.poc_fns_attachment.upload_staged_attachment", upload)

    result = run(config_file, source_file, "00_Inbox/附件/report.pdf", staging_dir)

    assert result == "00_Inbox/附件/report.pdf"
    assert source_file.exists()
    assert not captured["staged_file"].exists()
    assert captured["config"].vault == "obsidian"
