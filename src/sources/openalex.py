"""
OpenAlex API client.

OpenAlex stores abstracts as inverted indexes (word → list of positions) to
reduce storage size. This module reconstructs plain text from that format and
normalizes the work schema to match the Semantic Scholar output so the rest of
the pipeline can treat both sources identically.

No API key is required. Adding an email via the 'polite pool' (mailto param)
gives higher rate limits and is strongly recommended.
"""
import logging
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_SELECT = (
    "id,title,abstract_inverted_index,publication_year,"
    "cited_by_count,doi,authorships,primary_location"
)


def _reconstruct_abstract(inverted_index: dict | None) -> str:
    """Rebuild a plain-text abstract from OpenAlex's inverted-index representation."""
    if not inverted_index:
        return ""
    positions: dict[int, str] = {}
    for word, locs in inverted_index.items():
        for pos in locs:
            positions[pos] = word
    return " ".join(positions[i] for i in sorted(positions))


def _normalize(work: dict) -> dict:
    """Map OpenAlex work fields to the same schema used by SemanticScholar."""
    raw_doi = work.get("doi") or ""
    doi = raw_doi.replace("https://doi.org/", "").strip() or None

    authors = [
        {"name": a.get("author", {}).get("display_name", "")}
        for a in (work.get("authorships") or [])
    ]
    venue = (
        ((work.get("primary_location") or {}).get("source") or {})
        .get("display_name", "")
    )

    return {
        "paperId": work.get("id", ""),
        "title": work.get("title", ""),
        "abstract": _reconstruct_abstract(work.get("abstract_inverted_index")),
        "year": work.get("publication_year"),
        "citationCount": work.get("cited_by_count"),
        "externalIds": {"DOI": doi} if doi else {},
        "authors": authors,
        "venue": venue,
        "_source": "openalex",
    }


class OpenAlexClient:
    """Client for the OpenAlex Works API with cursor-based pagination."""

    BASE_URL = "https://api.openalex.org/works"

    def __init__(self, email: Optional[str] = None, rate_limit_delay: float = 0.5):
        self._session = requests.Session()
        self._email = email
        self._delay = rate_limit_delay

    def _params(self, extra: dict) -> dict:
        """Build request parameters, injecting the mailto field for the polite pool."""
        p = {"select": _SELECT, **extra}
        if self._email:
            p["mailto"] = self._email
        return p

    def search_all(self, query: str, max_results: int = 100) -> list[dict]:
        """
        Paginate through OpenAlex results using cursor-based pagination.

        OpenAlex supports up to 200 results per page and uses a cursor token
        (rather than numeric offsets) to avoid duplicate results across pages.
        """
        papers: list[dict] = []
        per_page = min(200, max_results)
        cursor = "*"

        while len(papers) < max_results:
            params = self._params({
                "search": query,
                "per_page": per_page,
                "cursor": cursor,
            })
            resp = self._session.get(self.BASE_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            time.sleep(self._delay)

            batch = data.get("results", [])
            if not batch:
                break

            papers.extend(_normalize(w) for w in batch)
            logger.debug(f"[openalex] fetched {len(papers)} so far")

            next_cursor = (data.get("meta") or {}).get("next_cursor")
            if not next_cursor:
                break
            cursor = next_cursor

        return papers[:max_results]
