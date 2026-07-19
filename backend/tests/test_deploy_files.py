from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_compose_exposes_only_caddy_and_persists_pocketbase_data():
    compose = (ROOT / "deploy/compose.yaml").read_text()

    assert "pocketbase_data:" in compose
    pocketbase = compose.split("  pocketbase:", 1)[1].split("  api:", 1)[0]
    api = compose.split("  api:", 1)[1].split("  worker:", 1)[0]
    assert "    ports:" not in pocketbase
    assert "    ports:" not in api


def test_env_example_contains_only_secret_placeholders():
    text = (ROOT / "deploy/.env.example").read_text()

    assert "change-me" in text
    assert "apiToken" not in text
