from dataclasses import dataclass
from urllib.parse import urlparse


class ClipError(Exception):
    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage


@dataclass(frozen=True)
class Article:
    title: str
    author: str
    source_url: str
    content_html: str


def validate_wechat_url(url: str) -> str:
    normalized = url.strip()
    parsed = urlparse(normalized)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "mp.weixin.qq.com"
        or not parsed.path.startswith("/s")
    ):
        raise ClipError("validate", "仅支持 HTTPS 微信公众号文章链接")
    return normalized
