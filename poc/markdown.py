import re
from html.parser import HTMLParser


class _MarkdownParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.image_count = 0
        self._href = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag in {"p", "div", "br", "ul", "ol"}:
            self.parts.append("\n\n")
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append(f"\n\n{'#' * int(tag[1])} ")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in {"strong", "b"}:
            self.parts.append("**")
        elif tag in {"em", "i"}:
            self.parts.append("*")
        elif tag == "code":
            self.parts.append("`")
        elif tag == "a":
            self._href = values.get("href") or ""
            self.parts.append("[")
        elif tag == "img":
            source = values.get("data-src") or values.get("src")
            if source:
                self.parts.append(f"\n\n![image]({source})")
                self.image_count += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"strong", "b"}:
            self.parts.append("**")
        elif tag in {"em", "i"}:
            self.parts.append("*")
        elif tag == "code":
            self.parts.append("`")
        elif tag == "a":
            self.parts.append(f"]({self._href})" if self._href else "]")
            self._href = ""
        elif tag in {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def html_to_markdown(content_html: str) -> tuple[str, int]:
    parser = _MarkdownParser()
    parser.feed(content_html)
    markdown = re.sub(r"\n{3,}", "\n\n", "".join(parser.parts)).strip()
    return markdown, parser.image_count
