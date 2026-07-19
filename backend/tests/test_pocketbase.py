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
