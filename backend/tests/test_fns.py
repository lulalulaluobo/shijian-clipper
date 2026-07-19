import pytest

from backend.app.errors import ApiError
from backend.app.fns import check_fns, parse_fns_json


def test_check_fns_reads_user_and_vault_without_posting():
    calls = []

    def get(url, headers):
        calls.append((url, headers))
        return {"data": [{"vault": "obsidian"}]} if url.endswith("/api/vault") else {"data": {"id": "me"}}

    result = check_fns("https://fns.example/", "secret", "obsidian", get)

    assert result == {"connected": True, "vault_exists": True, "vault_checked": True}
    assert [url for url, _ in calls] == ["https://fns.example/api/user/info", "https://fns.example/api/vault"]
    assert all(headers == {"token": "secret"} for _, headers in calls)


def test_check_fns_accepts_client_restricted_vault_listing():
    def get(url, headers):
        if url.endswith("/api/user/info"):
            return {"status": True, "data": {"id": "me"}}
        return {"status": False, "code": 314, "message": "Auth token Client restricted"}

    result = check_fns("https://fns.example", "secret", "obsidian", get)

    assert result == {"connected": True, "vault_exists": False, "vault_checked": False}


def test_parse_fns_json_requires_reference_project_fields():
    assert parse_fns_json('{"api":"https://fns.example/","apiToken":"secret","vault":"obsidian"}') == (
        "https://fns.example",
        "secret",
        "obsidian",
    )


def test_parse_fns_json_requires_a_root_https_endpoint():
    for api in ("http://fns.example", "https://fns.example/note", "https://user@fns.example"):
        with pytest.raises(ApiError, match="FNS 服务地址必须是 HTTPS 根地址"):
            parse_fns_json(f'{{"api":"{api}","apiToken":"secret","vault":"obsidian"}}')
