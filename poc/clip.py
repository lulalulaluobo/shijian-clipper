import argparse
import json
import sys
from typing import Callable
from urllib.request import Request, urlopen

from poc.markdown import html_to_markdown
from poc.wechat import ClipError, extract_article, validate_wechat_url


def run(
    url: str,
    fetch: Callable[[str], str],
) -> dict[str, object]:
    source_url = validate_wechat_url(url)
    try:
        source_html = fetch(source_url)
    except Exception as error:
        raise ClipError("fetch", "文章抓取失败") from error

    article = extract_article(source_html, source_url)
    markdown, images = html_to_markdown(article.content_html)
    return {
        "title": article.title,
        "author": article.author,
        "source_url": article.source_url,
        "markdown": markdown,
        "images": images,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取微信公众号文章并转换为 Markdown")
    parser.add_argument("url")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    def fetch(source_url: str) -> str:
        request = Request(source_url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=args.timeout) as response:
            return response.read().decode("utf-8")

    try:
        result = run(args.url, fetch)
    except ClipError as error:
        print(
            json.dumps({"stage": error.stage, "message": str(error)}, ensure_ascii=False),
            file=sys.stderr,
        )
        raise SystemExit(1)

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
