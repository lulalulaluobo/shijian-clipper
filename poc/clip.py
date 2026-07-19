import argparse
import json
import sys
from typing import Callable
from urllib.request import Request, urlopen

from poc.fns import FnsConfig, write_note
from poc.markdown import html_to_markdown
from poc.wechat import ClipError, extract_article, validate_wechat_url


def _yaml_value(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _build_note_content(title: str, author: str, source_url: str, markdown: str) -> str:
    return "\n".join(
        [
            "---",
            f"title: {_yaml_value(title)}",
            f"author: {_yaml_value(author)}",
            f"source: {_yaml_value(source_url)}",
            "---",
            "",
            f"# {title}",
            "",
            markdown,
        ]
    )


def run(
    url: str,
    config: FnsConfig,
    fetch: Callable[[str], str],
    post: Callable[[str, dict[str, str], dict[str, str]], dict[str, object]],
) -> dict[str, object]:
    source_url = validate_wechat_url(url)
    try:
        source_html = fetch(source_url)
    except Exception as error:
        raise ClipError("fetch", "文章抓取失败") from error

    article = extract_article(source_html, source_url)
    markdown, image_count = html_to_markdown(article.content_html)
    path = write_note(
        config,
        article.title,
        _build_note_content(article.title, article.author, article.source_url, markdown),
        post,
    )
    return {"title": article.title, "image_count": image_count, "path": path}


def main() -> None:
    parser = argparse.ArgumentParser(description="将微信公众号文章转存到 Fast Note Sync")
    parser.add_argument("url")
    parser.add_argument("--fns-base-url", required=True)
    parser.add_argument("--fns-token", required=True)
    parser.add_argument("--fns-vault", required=True)
    parser.add_argument("--target-dir", required=True)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    def fetch(source_url: str) -> str:
        request = Request(source_url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=args.timeout) as response:
            return response.read().decode("utf-8")

    def post(url: str, headers: dict[str, str], payload: dict[str, str]) -> dict[str, object]:
        request = Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={**headers, "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=args.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    try:
        result = run(
            args.url,
            FnsConfig(args.fns_base_url, args.fns_token, args.fns_vault, args.target_dir),
            fetch,
            post,
        )
    except ClipError as error:
        print(
            json.dumps({"stage": error.stage, "message": str(error)}, ensure_ascii=False),
            file=sys.stderr,
        )
        raise SystemExit(1)

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
