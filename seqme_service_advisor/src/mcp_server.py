#!/usr/bin/env python3

import json
import os
from pathlib import Path

#from mcp.server.fastmcp import FastMCP
#from mcp.types import ToolAnnotations

try:
    # MCP SDK v2
    from mcp.server import MCPServer

except ImportError:
    # MCP SDK v1
    from mcp.server.fastmcp import FastMCP as MCPServer

from mcp.types import ToolAnnotations

from kb import (
    DEFAULT_DB,
    get_page as db_get_page,
    search_faqs as db_search_faqs,
    search_services as db_search_services,
)


DB_PATH = Path(
    os.environ.get(
        "SEQME_DB",
        str(DEFAULT_DB),
    )
).expanduser().resolve()


mcp = MCPServer(
    "SEQme Service Knowledge Base"
)


READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    open_world_hint=False,
)


@mcp.tool(
    title="Search SEQme services",
    annotations=READ_ONLY,
)
def search_services(
    query: str,
    limit: int = 5,
) -> str:
    """
    Search the official local SEQme service catalogue.

    Use this when deciding which SEQme products or services
    could match a customer's scientific or technical problem.

    Search using concise English scientific/service terms,
    for example:
    'soil bacteria fungi microbiome'
    or
    'plasmid PCR sequencing'.

    The returned page_id can be passed to get_page() for
    detailed evidence before making a recommendation.
    """

    try:
        results = db_search_services(
            query=query,
            limit=limit,
            db_path=DB_PATH,
        )

        return json.dumps(
            {
                "query": query,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )

    except Exception as exc:
        return json.dumps(
            {
                "error": str(exc),
            },
            ensure_ascii=False,
        )


@mcp.tool(
    title="Read SEQme page",
    annotations=READ_ONLY,
)
def get_page(
    page_id: int,
    max_characters: int = 12000,
) -> str:
    """
    Retrieve the detailed contents of a SEQme page from
    the local knowledge database.

    Use page_id values returned by search_services()
    or search_faqs().

    Call this before making specific factual claims about
    service capabilities, requirements, prices, outputs,
    or other details.
    """

    try:
        page = db_get_page(
            page_id=page_id,
            db_path=DB_PATH,
        )

        if page is None:
            return json.dumps(
                {
                    "error": f"Page {page_id} not found."
                }
            )

        max_characters = max(
            1000,
            min(int(max_characters), 20000),
        )

        content = page["content"]

        truncated = len(content) > max_characters

        if truncated:
            content = content[:max_characters]

        page["content"] = content
        page["truncated"] = truncated

        return json.dumps(
            page,
            ensure_ascii=False,
            indent=2,
        )

    except Exception as exc:
        return json.dumps(
            {
                "error": str(exc),
            },
            ensure_ascii=False,
        )


@mcp.tool(
    title="Search SEQme FAQs",
    annotations=READ_ONLY,
)
def search_faqs(
    query: str,
    limit: int = 5,
) -> str:
    """
    Search official SEQme FAQ pages.

    Use this for sample requirements, ordering,
    library submission, shipping, preparation,
    or other practical questions.

    Search using concise English terms.
    """

    try:
        results = db_search_faqs(
            query=query,
            limit=limit,
            db_path=DB_PATH,
        )

        return json.dumps(
            {
                "query": query,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )

    except Exception as exc:
        return json.dumps(
            {
                "error": str(exc),
            },
            ensure_ascii=False,
        )


if __name__ == "__main__":
    mcp.run()

