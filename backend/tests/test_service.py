import hashlib

import pytest

from backend.app.service import ApiError, ClipService


class FakePocketBase:
    def __init__(self):
        self.code_hash = hashlib.sha256(b"invite-code").hexdigest()
        self.invites = {"invite-record": {"id": "invite-record", "code_hash": self.code_hash, "used_by": ""}}
        self.users = {}

    def list_records(self, collection, filter_value):
        if collection != "invite_codes" or self.code_hash not in filter_value:
            return []
        return [invite for invite in self.invites.values() if not invite["used_by"]]

    def create_user(self, email, password):
        user = {"id": f"user-{len(self.users) + 1}", "email": email}
        self.users[user["id"]] = user
        return user

    def update_record(self, collection, record_id, body):
        self.invites[record_id].update(body)

    def delete_record(self, collection, record_id):
        self.users.pop(record_id, None)

    def authenticate_user(self, token):
        if token != "valid-token":
            raise ApiError("登录已失效", 401)
        return "user-a"


def test_register_consumes_matching_invite_once():
    service = ClipService(FakePocketBase())

    created = service.register("invite-code", "a@example.com", "long-password")

    assert created == {"id": "user-1", "email": "a@example.com"}
    with pytest.raises(ApiError, match="邀请码无效或已使用"):
        service.register("invite-code", "b@example.com", "long-password")


def test_current_user_is_taken_only_from_authenticated_token():
    service = ClipService(FakePocketBase())

    assert service.current_user("valid-token") == "user-a"
    with pytest.raises(ApiError, match="登录已失效"):
        service.current_user("forged-user-id")
