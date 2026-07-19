from dataclasses import dataclass
from html.parser import HTMLParser
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


class _ArticleParser(HTMLParser):
    _VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.title = ""
        self.author_parts: list[str] = []
        self.fallback_title_parts: list[str] = []
        self.content_parts: list[str] = []
        self._author_depth = 0
        self._fallback_title_depth = 0
        self._content_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "meta" and values.get("property") == "og:title":
            self.title = values.get("content") or self.title

        element_id = values.get("id")
        if element_id == "js_name":
            self._author_depth = 1
        elif self._author_depth:
            self._author_depth += 1

        if element_id == "activity-name":
            self._fallback_title_depth = 1
        elif self._fallback_title_depth:
            self._fallback_title_depth += 1

        if element_id == "js_content":
            self._content_depth = 1
            return
        if self._content_depth:
            self.content_parts.append(self.get_starttag_text())
            if tag not in self._VOID_TAGS:
                self._content_depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._content_depth:
            self.content_parts.append(self.get_starttag_text())

    def handle_endtag(self, tag: str) -> None:
        if self._author_depth:
            self._author_depth -= 1
        if self._fallback_title_depth:
            self._fallback_title_depth -= 1
        if self._content_depth and tag not in self._VOID_TAGS:
            self._content_depth -= 1
            if self._content_depth:
                self.content_parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self._author_depth:
            self.author_parts.append(data)
        if self._fallback_title_depth:
            self.fallback_title_parts.append(data)
        if self._content_depth:
            self.content_parts.append(data)

    def handle_entityref(self, name: str) -> None:
        self._append_raw(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self._append_raw(f"&#{name};")

    def _append_raw(self, value: str) -> None:
        if self._content_depth:
            self.content_parts.append(value)


def extract_article(source_html: str, source_url: str) -> Article:
    parser = _ArticleParser()
    parser.feed(source_html)
    content_html = "".join(parser.content_parts).strip()
    if not content_html:
        raise ClipError("extract", "未找到文章正文")

    title = (parser.title or "".join(parser.fallback_title_parts) or "未命名文章").strip()
    return Article(
        title=title,
        author="".join(parser.author_parts).strip(),
        source_url=source_url,
        content_html=content_html,
    )
