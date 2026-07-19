import hashlib

from backend.scripts.create_invite import create_invite_code


def test_create_invite_code_is_url_safe_and_hashable():
    code = create_invite_code()

    assert len(code) >= 20
    assert hashlib.sha256(code.encode()).hexdigest()
