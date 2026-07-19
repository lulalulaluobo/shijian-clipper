import pytest
from cryptography.fernet import Fernet

from backend.app.config import Settings


def test_missing_encryption_key_raises_without_echoing_other_secrets(monkeypatch):
    monkeypatch.setenv("POCKETBASE_URL", "http://pocketbase:8090")
    monkeypatch.setenv("POCKETBASE_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("POCKETBASE_ADMIN_PASSWORD", "admin-secret")
    monkeypatch.delenv("FNS_ENCRYPTION_KEY", raising=False)

    with pytest.raises(ValueError, match="FNS_ENCRYPTION_KEY") as error:
        Settings.from_env()

    assert "admin-secret" not in str(error.value)


def test_reads_required_settings_from_environment(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("POCKETBASE_URL", "http://pocketbase:8090/")
    monkeypatch.setenv("POCKETBASE_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("POCKETBASE_ADMIN_PASSWORD", "admin-secret")
    monkeypatch.setenv("FNS_ENCRYPTION_KEY", key)

    settings = Settings.from_env()

    assert settings.pocketbase_url == "http://pocketbase:8090"
    assert settings.poll_interval_seconds == 2
