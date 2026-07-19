import socket

import pytest

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
