from cryptography.fernet import Fernet

from backend.app.crypto import decrypt_token, encrypt_token


def test_encrypt_token_round_trips_without_returning_plaintext():
    key = Fernet.generate_key().decode()

    encrypted = encrypt_token("secret-token", key)

    assert encrypted != "secret-token"
    assert decrypt_token(encrypted, key) == "secret-token"
