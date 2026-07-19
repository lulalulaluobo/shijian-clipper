import json

from backend.app.errors import ApiError


def parse_fns_json(raw: str) -> tuple[str, str, str]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ApiError("FNS 配置不是有效 JSON", 400) from error
    if not isinstance(value, dict):
        raise ApiError("FNS 配置必须是 JSON 对象", 400)
    api, token, vault = (value.get(name) for name in ("api", "apiToken", "vault"))
    if not all(isinstance(item, str) and item.strip() for item in (api, token, vault)):
        raise ApiError("FNS 配置缺少 api、apiToken 或 vault", 400)
    return api.strip().rstrip("/"), token.strip(), vault.strip()


def check_fns(base_url: str, token: str, vault: str, get) -> dict[str, bool]:
    headers = {"token": token}
    try:
        get(f"{base_url.rstrip('/')}/api/user/info", headers)
        response = get(f"{base_url.rstrip('/')}/api/vault", headers)
    except Exception as error:
        raise ApiError("Fast Note Sync 连接失败", 400) from error
    if isinstance(response, dict) and response.get("code") == 314:
        return {"connected": True, "vault_exists": False, "vault_checked": False}
    vaults = response.get("data") if isinstance(response, dict) else None
    if not isinstance(vaults, list):
        raise ApiError("Fast Note Sync 响应无效", 400)
    return {
        "connected": True,
        "vault_exists": any(isinstance(item, dict) and item.get("vault") == vault for item in vaults),
        "vault_checked": True,
    }
