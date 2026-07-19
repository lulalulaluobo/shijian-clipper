from cryptography.fernet import Fernet

from backend.app.service import ClipService


class FakePocketBase:
    def __init__(self):
        self.settings = {}

    def list_records(self, collection, filter_value):
        return [value for value in self.settings.values() if value["user"] in filter_value]

    def create_record(self, collection, body):
        record = {"id": "setting-1", **body}
        self.settings[record["id"]] = record
        return record

    def update_record(self, collection, record_id, body):
        self.settings[record_id].update(body)
        return self.settings[record_id]


def test_get_settings_masks_saved_token():
    service = ClipService(FakePocketBase(), Fernet.generate_key().decode())

    saved = service.save_fns_settings(
        "user-a",
        '{"api":"https://fns.example","apiToken":"secret","vault":"obsidian"}',
        "00_Inbox/微信公众号",
    )

    assert saved["token_saved"] is True
    assert "secret" not in repr(saved)
    assert service.get_fns_settings("user-a")["target_dir"] == "00_Inbox/微信公众号"
