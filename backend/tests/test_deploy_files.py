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


def test_migration_uses_pocketbase_default_users_collection():
    migration = (ROOT / "deploy/pocketbase/pb_migrations/1710000000_initial.js").read_text()

    assert 'app.findCollectionByNameOrId("users")' in migration
    assert 'name: "users"' not in migration


def test_invite_permission_migration_adds_user_boolean_field():
    migration = (ROOT / "deploy/pocketbase/pb_migrations/1710000001_invite_permission.js").read_text()

    assert 'new BoolField({ name: "can_create_invites" })' in migration


def test_access_expiry_migration_adds_invite_code_and_user_expiry_fields():
    migration = (ROOT / "deploy/pocketbase/pb_migrations/1710000002_user_access_expiry.js").read_text()

    assert 'new TextField({ name: "code"' in migration
    assert 'new DateField({ name: "access_expires_at" })' in migration


def test_vps_compose_publishes_only_loopback_ports_without_host_network():
    compose = (ROOT / "deploy/compose.vps.yaml").read_text()

    assert "network_mode: host" not in compose
    assert '"127.0.0.1:18080:8000"' in compose
    assert '"127.0.0.1:18081:8090"' in compose


def test_notes_migration_creates_collection_with_required_fields():
    migration = (ROOT / "deploy/pocketbase/pb_migrations/1710000005_create_notes_table.js").read_text()

    assert 'name: "notes"' in migration
    assert '{ name: "user", type: "relation", required: true, collectionId: users.id' in migration
    assert '{ name: "source_url", type: "url", required: true }' in migration
    assert '{ name: "title", type: "text", required: true }' in migration
    assert '{ name: "filename", type: "text", required: true }' in migration
    assert '{ name: "content_md", type: "text" }' in migration
    assert '{ name: "images", type: "json" }' in migration
    assert 'values: ["article", "attachment"]' in migration
    assert '{ name: "attachment_b64", type: "text" }' in migration
    assert '{ name: "delivered", type: "number" }' in migration  # bool 字段在 PocketBase 0.38 filter 里有 bug
    # MVP 阶段不声明索引（PocketBase collection 创建阶段无法引用 created 自动字段）
    assert "idx_notes_user_delivered" not in migration
    assert "idx_notes_created" not in migration


def test_drop_fns_settings_migration_deletes_collection():
    migration = (ROOT / "deploy/pocketbase/pb_migrations/1710000006_drop_fns_settings.js").read_text()

    assert 'app.findCollectionByNameOrId("fns_settings")' in migration
    assert 'app.delete(' in migration
