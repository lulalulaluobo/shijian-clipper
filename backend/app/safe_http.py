import ipaddress
import json
import socket
import uuid
from http.client import HTTPSConnection
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


MAX_RESPONSE_BYTES = 5 * 1024 * 1024


class UnsafeUrlError(ValueError):
    pass


class _PinnedHttpsConnection(HTTPSConnection):
    def __init__(self, host: str, port: int, address: str, timeout: int) -> None:
        super().__init__(host, port=port, timeout=timeout)
        self.address = address

    def connect(self) -> None:
        sock = socket.create_connection((self.address, self.port), self.timeout, self.source_address)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def normalize_https_root_url(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except ValueError as error:
        raise UnsafeUrlError("FNS 服务地址必须是 HTTPS 根地址") from error
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise UnsafeUrlError("FNS 服务地址必须是 HTTPS 根地址")
    host = parsed.hostname.lower()
    netloc = host if port in {None, 443} else f"{host}:{port}"
    return urlunsplit(("https", netloc, "", "", ""))


def validate_public_https_url(url: str, resolver=socket.getaddrinfo) -> str:
    normalized = normalize_https_root_url(url)
    parsed = urlsplit(normalized)
    _resolve_public_address(parsed.hostname or "", parsed.port or 443, resolver)
    return normalized


def request_public_json(
    url: str,
    *,
    method: str,
    headers: dict[str, str],
    payload: dict[str, str] | None = None,
    timeout: int = 30,
    expected_host: str | None = None,
    allow_private_addresses: bool = False,
) -> dict:
    content = request_public_bytes(
        url,
        method=method,
        headers=headers,
        payload=payload,
        timeout=timeout,
        expected_host=expected_host,
        allow_private_addresses=allow_private_addresses,
    )
    try:
        value = json.loads(content.decode())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("远程服务响应不是 JSON") from error
    if not isinstance(value, dict):
        raise ValueError("远程服务响应无效")
    return value


def request_public_text(
    url: str,
    *,
    headers: dict[str, str],
    timeout: int = 30,
    expected_host: str | None = None,
    allow_private_addresses: bool = False,
) -> str:
    try:
        return request_public_bytes(
            url,
            method="GET",
            headers=headers,
            timeout=timeout,
            expected_host=expected_host,
            allow_private_addresses=allow_private_addresses,
        ).decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("远程服务响应不是 UTF-8") from error


def request_public_multipart_file(
    url: str,
    *,
    headers: dict[str, str],
    fields: dict[str, str],
    file_path: Path,
    timeout: int = 30,
    expected_host: str | None = None,
    allow_private_addresses: bool = False,
) -> dict:
    try:
        parsed = urlsplit(url)
        port = parsed.port or 443
    except ValueError as error:
        raise UnsafeUrlError("只允许访问公网 HTTPS 地址") from error
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise UnsafeUrlError("只允许访问公网 HTTPS 地址")
    if not file_path.is_file():
        raise ValueError("附件暂存文件不存在")
    host = parsed.hostname.lower()
    if expected_host is not None and host != expected_host:
        raise UnsafeUrlError("远程地址不受允许")
    address = _resolve_public_address(host, port, socket.getaddrinfo, allow_private_addresses)
    boundary = f"----Shijian{uuid.uuid4().hex}"
    prefix = b"".join(
        _multipart_field(boundary, name, value)
        for name, value in fields.items()
    ) + _multipart_file_header(boundary, file_path.name)
    suffix = f"\r\n--{boundary}--\r\n".encode()
    request_headers = dict(headers)
    request_headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    request_headers["Content-Length"] = str(len(prefix) + file_path.stat().st_size + len(suffix))
    path = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))

    connection = _PinnedHttpsConnection(host, port, address, timeout)
    try:
        connection.putrequest("POST", path)
        for name, value in request_headers.items():
            connection.putheader(name, value)
        connection.endheaders()
        connection.send(prefix)
        with file_path.open("rb") as file:
            while chunk := file.read(64 * 1024):
                connection.send(chunk)
        connection.send(suffix)
        response = connection.getresponse()
        content = response.read(MAX_RESPONSE_BYTES + 1)
    finally:
        connection.close()
    if not 200 <= response.status < 300:
        raise ValueError("远程服务响应失败")
    if len(content) > MAX_RESPONSE_BYTES:
        raise ValueError("远程服务响应过大")
    try:
        value = json.loads(content.decode())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("远程服务响应不是 JSON") from error
    if not isinstance(value, dict):
        raise ValueError("远程服务响应无效")
    return value


def request_public_bytes(
    url: str,
    *,
    method: str,
    headers: dict[str, str],
    payload: dict[str, str] | None = None,
    timeout: int = 30,
    expected_host: str | None = None,
    allow_private_addresses: bool = False,
) -> bytes:
    try:
        parsed = urlsplit(url)
        port = parsed.port or 443
    except ValueError as error:
        raise UnsafeUrlError("只允许访问公网 HTTPS 地址") from error
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise UnsafeUrlError("只允许访问公网 HTTPS 地址")
    host = parsed.hostname.lower()
    if expected_host is not None and host != expected_host:
        raise UnsafeUrlError("远程地址不受允许")
    address = _resolve_public_address(host, port, socket.getaddrinfo, allow_private_addresses)
    path = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
    body = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    request_headers = dict(headers)
    if body is not None:
        request_headers["Content-Type"] = "application/json"

    connection = _PinnedHttpsConnection(host, port, address, timeout)
    try:
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        content = response.read(MAX_RESPONSE_BYTES + 1)
    finally:
        connection.close()
    if not 200 <= response.status < 300:
        raise ValueError("远程服务响应失败")
    if len(content) > MAX_RESPONSE_BYTES:
        raise ValueError("远程服务响应过大")
    return content


def _multipart_field(boundary: str, name: str, value: str) -> bytes:
    return f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()


def _multipart_file_header(boundary: str, filename: str) -> bytes:
    safe_name = filename.replace("\r", "").replace("\n", "").replace('"', "")
    return f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{safe_name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()


def _resolve_public_address(host: str, port: int, resolver, allow_private_addresses: bool = False) -> str:
    try:
        resolved = resolver(host, port, type=socket.SOCK_STREAM)
    except OSError as error:
        raise UnsafeUrlError("只允许访问公网 HTTPS 地址") from error
    addresses = {item[4][0] for item in resolved}
    if not addresses:
        raise UnsafeUrlError("只允许访问公网 HTTPS 地址")
    try:
        public_addresses = sorted(address for address in addresses if ipaddress.ip_address(address).is_global)
        if public_addresses:
            return public_addresses[0]
        if not allow_private_addresses:
            raise UnsafeUrlError("只允许访问公网 HTTPS 地址")
    except ValueError as error:
        raise UnsafeUrlError("只允许访问公网 HTTPS 地址") from error
    return sorted(addresses)[0]
