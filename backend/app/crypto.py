from cryptography.fernet import Fernet


def encrypt_token(token: str, key: str) -> str:
    return Fernet(key.encode()).encrypt(token.encode()).decode()


def decrypt_token(ciphertext: str, key: str) -> str:
    return Fernet(key.encode()).decrypt(ciphertext.encode()).decode()
