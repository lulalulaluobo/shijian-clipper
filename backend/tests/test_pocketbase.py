import json
from unittest.mock import MagicMock

from backend.app.pocketbase import PocketBaseClient


def test_request_adds_bearer_token_and_parses_json():
    response = MagicMock()
    response.read.return_value = b'{"id":"record-1"}'
    opener = MagicMock()
    opener.return_value.__enter__.return_value = response
    client = PocketBaseClient("http://pocketbase:8090", "admin@example.com", "secret", opener=opener)

    result = client.request("POST", "/api/example", token="user-token", body={"name": "value"})

    request = opener.call_args.args[0]
    assert result == {"id": "record-1"}
    assert request.get_header("Authorization") == "Bearer user-token"
    assert json.loads(request.data) == {"name": "value"}


def test_login_user_uses_pocketbase_user_collection():
    response = MagicMock()
    response.read.return_value = b'{"token":"session-token","record":{"id":"user-a"}}'
    opener = MagicMock()
    opener.return_value.__enter__.return_value = response
    client = PocketBaseClient("http://pocketbase:8090", "admin@example.com", "secret", opener=opener)

    result = client.login_user("a@example.com", "long-password")

    request = opener.call_args.args[0]
    assert request.full_url.endswith("/api/collections/users/auth-with-password")
    assert json.loads(request.data) == {"identity": "a@example.com", "password": "long-password"}
    assert result["token"] == "session-token"


def _stub_opener_with_items(items):
    """构造一个 opener mock，对 admin auth 与 records 查询返回不同响应。"""
    responses = iter([
        b'{"token":"admin-token"}',                       # _admin_token POST
        json.dumps({"items": items}).encode(),            # list_records_sorted GET
    ])
    opener = MagicMock()
    opener.return_value.__enter__.return_value.read.side_effect = lambda: next(responses)
    return opener


def test_list_records_sorted_passes_sort_and_filter_to_query():
    items = [{"id": "n2", "created": "2026-07-19T10:00:00Z"}, {"id": "n1", "created": "2026-07-19T09:00:00Z"}]
    opener = _stub_opener_with_items(items)
    client = PocketBaseClient("http://pocketbase:8090", "admin@example.com", "secret", opener=opener)

    result = client.list_records_sorted(
        "notes",
        'user = "u1" && delivered = 0',
        sort="created",
        per_page=50,
    )

    # 第二次调用（GET records）的 Request URL 应同时含 filter、sort、perPage
    list_request = opener.call_args_list[1].args[0]
    full_url = list_request.full_url
    assert "sort=created" in full_url
    assert "perPage=50" in full_url
    assert "delivered+%3D+0" in full_url or "delivered+0" in full_url or "delivered" in full_url
    assert result == items


def test_list_records_sorted_passes_page_to_query():
    opener = _stub_opener_with_items([])
    client = PocketBaseClient("http://pocketbase:8090", "admin@example.com", "secret", opener=opener)

    client.list_records_sorted("notes", 'user = "u1" && delivered = 0', sort="id", per_page=200, page=2)

    assert "page=2" in opener.call_args_list[1].args[0].full_url
