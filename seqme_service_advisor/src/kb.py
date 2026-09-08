#!/usr/bin/env python3

import re
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / "data" / "seqme.db"


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "have",
    "i",
    "in",
    "is",
    "it",
    "my",
    "of",
    "on",
    "or",
    "our",
    "the",
    "to",
    "we",
    "want",
    "which",
    "with",
    "would",
    "need",
    "some",
}


def connect(db_path: Path = DEFAULT_DB):
    if not db_path.exists():
        raise FileNotFoundError(
            f"Knowledge database does not exist: {db_path}"
        )

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row

    return con


def make_fts_query(query: str) -> str:
    """
    Convert natural-language text into a safe broad FTS query.

    Example:
        soil bacterial fungal community

    becomes approximately:
        "soil" OR "bacterial" OR "fungal" OR "community"
    """

    tokens = re.findall(
        r"\w+",
        query.lower(),
        flags=re.UNICODE,
    )

    useful = []

    for token in tokens:
        if len(token) < 2:
            continue

        if token in STOPWORDS:
            continue

        if token not in useful:
            useful.append(token)

    useful = useful[:15]

    if not useful:
        raise ValueError(
            "Search query does not contain useful search terms."
        )

    return " OR ".join(
        f'"{token}"'
        for token in useful
    )


def _search(
    query: str,
    page_type: str,
    limit: int = 5,
    db_path: Path = DEFAULT_DB,
):
    limit = max(1, min(int(limit), 10))

    fts_query = make_fts_query(query)

    con = connect(db_path)

    rows = con.execute(
        """
        SELECT
            rowid AS page_id,
            title,
            url,
            page_type,
            bm25(
                pages_fts,
                5.0,
                1.0,
                0.0,
                0.0
            ) AS rank,
            snippet(
                pages_fts,
                1,
                '[MATCH]',
                '[/MATCH]',
                ' ... ',
                40
            ) AS snippet
        FROM pages_fts
        WHERE
            pages_fts MATCH ?
            AND page_type = ?
        ORDER BY rank
        LIMIT ?
        """,
        (
            fts_query,
            page_type,
            limit,
        ),
    ).fetchall()

    con.close()

    return [
        dict(row)
        for row in rows
    ]


def search_services(
    query: str,
    limit: int = 5,
    db_path: Path = DEFAULT_DB,
):
    return _search(
        query=query,
        page_type="service",
        limit=limit,
        db_path=db_path,
    )


def search_faqs(
    query: str,
    limit: int = 5,
    db_path: Path = DEFAULT_DB,
):
    return _search(
        query=query,
        page_type="faq",
        limit=limit,
        db_path=db_path,
    )


def get_page(
    page_id: int,
    db_path: Path = DEFAULT_DB,
):
    con = connect(db_path)

    row = con.execute(
        """
        SELECT
            id AS page_id,
            title,
            url,
            page_type,
            content,
            fetched_at
        FROM pages
        WHERE id = ?
        """,
        (int(page_id),),
    ).fetchone()

    con.close()

    if row is None:
        return None

    return dict(row)
