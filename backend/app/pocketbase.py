import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.app.errors import ApiError


class PocketBaseClient:
    def __init__(self, base_url: str, admin_email: str, admin_password: str, opener=urlopen) -> None:
        self.base_url = base_url.rstrip("/")
        self.admin_email = admin_email
        self.admin_password = admin_password
        self.opener = opener

    def request(self, method: str, path: str, *, token: str | None = None, body: dict | None = None) -> dict:
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode()
            headers["Content-Type"] = "application/json"
        request = Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        try:
            with self.opener(request, timeout=30) as response:
                raw_bytes = response.read()
                if not raw_bytes:
                    return {}
                payload = json.loads(raw_bytes.decode())
        except (HTTPError, URLError, OSError, ValueError) as error:
            raise ApiError("后端服务请求失败", 502) from error
        if not isinstance(payload, dict):
            raise ApiError("后端服务响应无效", 502)
        return payload

    def _admin_token(self) -> str:
        payload = self.request(
            "POST",
            "/api/collections/_superusers/auth-with-password",
            body={"identity": self.admin_email, "password": self.admin_password},
        )
        token = payload.get("token")
        if not isinstance(token, str) or not token:
            raise ApiError("后端管理员认证失败", 502)
        return token

    def list_records(self, collection: str, filter_value: str, per_page: int = 1) -> list[dict]:
        query = urlencode({"filter": filter_value, "perPage": per_page})
        payload = self.request("GET", f"/api/collections/{collection}/records?{query}", token=self._admin_token())
        items = payload.get("items")
        return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []

    def list_records_sorted(
        self,
        collection: str,
        filter_value: str,
        sort: str = "created",
        per_page: int = 50,
        page: int = 1,
    ) -> list[dict]:
        """按指定字段排序查询记录，用于 notes 增量同步（按 created 升序返回最旧的未同步项）。"""
        query = urlencode({"filter": filter_value, "sort": sort, "perPage": per_page, "page": page})
        payload = self.request("GET", f"/api/collections/{collection}/records?{query}", token=self._admin_token())
        items = payload.get("items")
        return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []

    def create_user(self, email: str, password: str) -> dict:
        return self.request(
            "POST",
            "/api/collections/users/records",
            token=self._admin_token(),
            body={"email": email, "password": password, "passwordConfirm": password},
        )

    def create_record(self, collection: str, body: dict) -> dict:
        return self.request(
            "POST",
            f"/api/collections/{collection}/records",
            token=self._admin_token(),
            body=body,
        )

    def update_record(self, collection: str, record_id: str, body: dict) -> dict:
        return self.request(
            "PATCH",
            f"/api/collections/{collection}/records/{record_id}",
            token=self._admin_token(),
            body=body,
        )

    def delete_record(self, collection: str, record_id: str) -> None:
        self.request("DELETE", f"/api/collections/{collection}/records/{record_id}", token=self._admin_token())

    def authenticate_user(self, token: str) -> str:
        try:
            payload = self.request("POST", "/api/collections/users/auth-refresh", token=token)
        except ApiError as error:
            cause = error.__cause__
            if isinstance(cause, HTTPError) and cause.code in (400, 401, 403, 404):
                raise ApiError("登录已失效", 401) from error
            raise
        record = payload.get("record")
        user_id = record.get("id") if isinstance(record, dict) else None
        if not isinstance(user_id, str) or not user_id:
            raise ApiError("登录已失效", 401)
        return user_id

    def login_user(self, email: str, password: str) -> dict:
        return self.request(
            "POST",
            "/api/collections/users/auth-with-password",
            body={"identity": email, "password": password},
        )
