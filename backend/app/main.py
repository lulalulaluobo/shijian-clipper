from backend.app.api import create_app
from backend.app.config import Settings
from backend.app.pocketbase import PocketBaseClient
from backend.app.service import ClipService


settings = Settings.from_env()
app = create_app(
    ClipService(
        PocketBaseClient(settings.pocketbase_url, settings.pocketbase_admin_email, settings.pocketbase_admin_password),
    )
)
