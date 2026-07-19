import pytest

from backend.app.config import Settings


def test_missing_admin_password_raises_without_echoing_other_secrets(monkeypatch):
    monkeypatch.setenv("POCKETBASE_URL", "http://pocketbase:8090")
    monkeypatch.setenv("POCKETBASE_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.delenv("POCKETBASE_ADMIN_PASSWORD", raising=False)

    with pytest.raises(ValueError, match="POCKETBASE_ADMIN_PASSWORD") as error:
        Settings.from_env()

    assert "admin@example.com" not in str(error.value)


def test_reads_required_settings_from_environment(monkeypatch):
    monkeypatch.setenv("POCKETBASE_URL", "http://pocketbase:8090/")
    monkeypatch.setenv("POCKETBASE_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("POCKETBASE_ADMIN_PASSWORD", "admin-secret")

    settings = Settings.from_env()

    assert settings.pocketbase_url == "http://pocketbase:8090"
    assert settings.poll_interval_seconds == 2
