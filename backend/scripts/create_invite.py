import hashlib
import os
import secrets

from backend.app.pocketbase import PocketBaseClient


def create_invite_code() -> str:
    return secrets.token_urlsafe(18)


def main() -> None:
    base_url = os.environ["POCKETBASE_URL"]
    admin_email = os.environ["POCKETBASE_ADMIN_EMAIL"]
    admin_password = os.environ["POCKETBASE_ADMIN_PASSWORD"]
    code = create_invite_code()
    client = PocketBaseClient(base_url, admin_email, admin_password)
    client.create_record("invite_codes", {"code_hash": hashlib.sha256(code.encode()).hexdigest()})
    print(code)


if __name__ == "__main__":
    main()
