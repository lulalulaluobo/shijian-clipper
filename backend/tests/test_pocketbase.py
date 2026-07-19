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
