#!/usr/bin/env python3

import argparse
import hashlib
import re
import sqlite3
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup


DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "seqme.db"

SEEDS = [
    "https://www.seqme.eu/en/products-services/",
    "https://www.seqme.eu/en/faqs/",
]

ALLOWED_HOSTS = {
    "seqme.eu",
    "www.seqme.eu",
}

SKIP_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".zip", ".jpg", ".jpeg", ".png", ".gif",
    ".svg", ".mp4", ".avi", ".gz", ".tar",
}


def canonicalize_url(url: str) -> str | None:
    """Normalize SEQme URLs and remove query strings/fragments."""
    try:
        parsed = urlsplit(url)
    except Exception:
        return None

    host = parsed.netloc.lower()

    if not host:
        return None

    if host not in ALLOWED_HOSTS:
        return None

    path = re.sub(r"/+", "/", parsed.path)

    if path != "/" and path.endswith("/"):
        path = path[:-1]

    return urlunsplit(
        (
            "https",
            "www.seqme.eu",
            path,
            "",
            "",
        )
    )


def allowed_url(url: str) -> bool:
    parsed = urlsplit(url)

    if parsed.netloc.lower() not in ALLOWED_HOSTS:
        return False

    path = parsed.path.lower()

    for ext in SKIP_EXTENSIONS:
        if path.endswith(ext):
            return False

    # First version of the knowledge base:
    # only products/services and FAQs.
    return (
        path == "/en/products-services"
        or path.startswith("/en/products-services/")
        or path == "/en/faqs"
        or path.startswith("/en/faqs/")
    )


def page_type(url: str) -> str:
    path = urlsplit(url).path.rstrip("/")

    if path == "/en/products-services":
        return "catalog"

    if path.startswith("/en/products-services/"):
        return "service"

    if path.startswith("/en/faqs"):
        return "faq"

    return "other"


def clean_text(soup: BeautifulSoup) -> tuple[str, str]:
    """Extract readable page title and main text."""

    # Remove elements that are useless for the knowledge base.
    for tag in soup.find_all(
        [
            "script",
            "style",
            "noscript",
            "svg",
            "nav",
            "header",
            "footer",
            "form",
        ]
    ):
        tag.decompose()

    root = (
        soup.find("main")
        or soup.find(attrs={"role": "main"})
        or soup.body
        or soup
    )

    h1 = root.find("h1") if root else None

    if h1:
        title = h1.get_text(" ", strip=True)
    elif soup.title:
        title = soup.title.get_text(" ", strip=True)
    else:
        title = "Untitled SEQme page"

    raw = root.get_text("\n", strip=True)

    lines = []

    previous = None

    for line in raw.splitlines():
        line = re.sub(r"\s+", " ", line).strip()

        if not line:
            continue

        # Remove immediate repeated lines.
        if line == previous:
            continue

        lines.append(line)
        previous = line

    text = "\n".join(lines)

    return title, text


def create_database(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(db_path)

    con.executescript(
        """
        PRAGMA journal_mode=WAL;

        CREATE TABLE IF NOT EXISTS pages (
            id INTEGER PRIMARY KEY,
            url TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            page_type TEXT NOT NULL,
            content TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            fetched_at TEXT NOT NULL
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
            title,
            content,
            url UNINDEXED,
            page_type UNINDEXED,
            tokenize='unicode61 remove_diacritics 2'
        );

        CREATE INDEX IF NOT EXISTS idx_pages_type
        ON pages(page_type);
        """
    )

    return con


def store_page(
    con: sqlite3.Connection,
    url: str,
    title: str,
    ptype: str,
    content: str,
):
    content_hash = hashlib.sha256(
        content.encode("utf-8")
    ).hexdigest()

    fetched_at = datetime.now(timezone.utc).isoformat()

    con.execute(
        """
        INSERT INTO pages (
            url,
            title,
            page_type,
            content,
            content_hash,
            fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?)

        ON CONFLICT(url) DO UPDATE SET
            title = excluded.title,
            page_type = excluded.page_type,
            content = excluded.content,
            content_hash = excluded.content_hash,
            fetched_at = excluded.fetched_at
        """,
        (
            url,
            title,
            ptype,
            content,
            content_hash,
            fetched_at,
        ),
    )


def rebuild_fts(con: sqlite3.Connection):
    con.execute("DELETE FROM pages_fts")

    con.execute(
        """
        INSERT INTO pages_fts (
            rowid,
            title,
            content,
            url,
            page_type
        )
        SELECT
            id,
            title,
            content,
            url,
            page_type
        FROM pages
        """
    )

    con.commit()


def crawl(
    db_path: Path,
    max_pages: int,
    delay: float,
    reset: bool,
):
    con = create_database(db_path)

    if reset:
        con.execute("DELETE FROM pages")
        con.execute("DELETE FROM pages_fts")
        con.commit()

    session = requests.Session()

    session.headers.update(
        {
            "User-Agent": (
                "SEQme-Service-Advisor/0.1 "
                "(internal educational prototype)"
            )
        }
    )

    queue = deque()

    for seed in SEEDS:
        url = canonicalize_url(seed)

        if url:
            queue.append(url)

    seen = set()

    downloaded = 0

    while queue and downloaded < max_pages:
        url = queue.popleft()

        if url in seen:
            continue

        seen.add(url)

        if not allowed_url(url):
            continue

        print(f"[{downloaded + 1}/{max_pages}] {url}")

        try:
            response = session.get(
                url,
                timeout=30,
                allow_redirects=True,
            )
        except requests.RequestException as exc:
            print(f"  ERROR: {exc}")
            continue

        if response.status_code != 200:
            print(f"  HTTP {response.status_code}")
            continue

        content_type = response.headers.get(
            "Content-Type",
            "",
        ).lower()

        if "text/html" not in content_type:
            print(f"  skipping content type: {content_type}")
            continue

        final_url = canonicalize_url(response.url)

        if not final_url:
            continue

        soup = BeautifulSoup(response.text, "lxml")

        # Discover links BEFORE removing nav/etc.
        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href", "").strip()

            if not href:
                continue

            if href.startswith(
                ("mailto:", "tel:", "javascript:", "#")
            ):
                continue

            candidate = urljoin(final_url, href)
            candidate = canonicalize_url(candidate)

            if not candidate:
                continue

            if allowed_url(candidate) and candidate not in seen:
                queue.append(candidate)

        title, content = clean_text(soup)

        if len(content) < 50:
            print("  skipping almost-empty page")
            continue

        store_page(
            con,
            final_url,
            title,
            page_type(final_url),
            content,
        )

        con.commit()

        downloaded += 1

        if delay > 0:
            time.sleep(delay)

    print("\nRebuilding full-text index...")
    rebuild_fts(con)

    print("\nDatabase summary:")

    for row in con.execute(
        """
        SELECT page_type, COUNT(*)
        FROM pages
        GROUP BY page_type
        ORDER BY page_type
        """
    ):
        print(f"  {row[0]}: {row[1]}")

    print(f"\nDatabase: {db_path}")

    con.close()


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
    )

    parser.add_argument(
        "--max-pages",
        type=int,
        default=250,
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=0.25,
        help="Delay between requests in seconds.",
    )

    parser.add_argument(
        "--no-reset",
        action="store_true",
        help="Keep existing database rows.",
    )

    args = parser.parse_args()

    crawl(
        db_path=args.db,
        max_pages=args.max_pages,
        delay=args.delay,
        reset=not args.no_reset,
    )


if __name__ == "__main__":
    main()

