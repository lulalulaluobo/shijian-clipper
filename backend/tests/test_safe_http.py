import socket
from pathlib import Path

import pytest

from backend.app import safe_http
from backend.app.safe_http import UnsafeUrlError, validate_public_https_url


def test_rejects_private_address_before_connecting():
    def private_resolver(*_, **__):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]

    with pytest.raises(UnsafeUrlError, match="公网 HTTPS"):
        validate_public_https_url("https://fns.example", resolver=private_resolver)


def test_accepts_public_https_root_url():
    def public_resolver(*_, **__):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 443))]

    assert validate_public_https_url("https://fns.example/", resolver=public_resolver) == "https://fns.example"


def test_multipart_upload_streams_file_and_returns_json(tmp_path: Path, monkeypatch):
    staged_file = tmp_path / "attachment.pdf"
    staged_file.write_bytes(b"binary-file-content")
    captured = {"headers": [], "sent": []}

    class Response:
        status = 200

        def read(self, _):
            return b'{"status": true, "data": {"path": "Inbox/attachment.pdf"}}'

    class Connection:
        def __init__(self, *_):
            pass

        def putrequest(self, method, path):
            captured["method"] = method
            captured["path"] = path

        def putheader(self, name, value):
            captured["headers"].append((name, value))

        def endheaders(self):
            pass

        def send(self, content):
            captured["sent"].append(content)

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr(safe_http, "_PinnedHttpsConnection", Connection)
    monkeypatch.setattr(safe_http, "_resolve_public_address", lambda *_: "1.1.1.1")

    result = safe_http.request_public_multipart_file(
        "https://fns.example/api/file",
        headers={"token": "secret"},
        fields={"vault": "obsidian", "path": "Inbox/attachment.pdf", "ctime": "1", "mtime": "2"},
        file_path=staged_file,
    )

    assert result == {"status": True, "data": {"path": "Inbox/attachment.pdf"}}
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/file"
    assert ("token", "secret") in captured["headers"]
    assert any(name == "Content-Type" and "multipart/form-data" in value for name, value in captured["headers"])
    assert b"binary-file-content" in captured["sent"]
