"""
OpenAlex Works API client (cursor pagination).

Abstracts arrive as inverted indexes and are rebuilt to plain text. Adding an
email (config.yaml -> sources.openalex.email) puts requests in the polite pool.
"""
import logging
import time
from typing import Optional

import requests

from src.utils.records import classify_publication_type, normalize_doi

logger = logging.getLogger(__name__)

BASE_URL = "https://api.openalex.org/works"
_SELECT = ("id,title,abstract_inverted_index,publication_year,cited_by_count,doi,"
           "authorships,primary_location,type,open_access")


def _reconstruct_abstract(inverted_index: dict | None) -> str:
    if not inverted_index:
        return ""
    positions = {pos: word for word, locs in inverted_index.items() for pos in locs}
    return " ".join(positions[i] for i in sorted(positions))


def _normalize(work: dict) -> dict:
    doi = normalize_doi(work.get("doi"))
    source = (work.get("primary_location") or {}).get("source") or {}
    return {
        "title": work.get("title") or "",
        "abstract": _reconstruct_abstract(work.get("abstract_inverted_index")),
        "year": work.get("publication_year"),
        "citationCount": work.get("cited_by_count"),
        "externalIds": {"DOI": doi} if doi else {},
        "authors": [
            {"name": (a.get("author") or {}).get("display_name", "")}
            for a in (work.get("authorships") or []) if (a.get("author") or {}).get("display_name")
        ],
        "venue": source.get("display_name") or "",
        # OpenAlex labels conference papers as type "article"; the source type tells them apart.
        "publicationType": classify_publication_type(source.get("type"), work.get("type")),
        "openAccessPdf": (work.get("open_access") or {}).get("oa_url"),
        "_source": "openalex",
    }


class OpenAlexClient:
    def __init__(self, email: Optional[str] = None, rate_limit_delay: float = 0.2):
        self._session = requests.Session()
        self._email = email
        self._delay = rate_limit_delay

    def search_all(self, query: str, max_results: int = 100,
                   year_from: int | None = None, year_to: int | None = None) -> list[dict]:
        papers: list[dict] = []
        cursor = "*"
        params = {"select": _SELECT, "search": query}
        if year_from or year_to:
            params["filter"] = f"publication_year:{year_from or ''}-{year_to or ''}"
        if self._email:
            params["mailto"] = self._email
        while len(papers) < max_results:
            per_page = min(200, max_results - len(papers))
            resp = self._session.get(BASE_URL, params={**params, "per_page": per_page, "cursor": cursor},
                                     timeout=30)
            resp.raise_for_status()
            data = resp.json()
            time.sleep(self._delay)
            batch = data.get("results") or []
            if not batch:
                break
            papers.extend(_normalize(w) for w in batch)
            cursor = (data.get("meta") or {}).get("next_cursor")
            if not cursor:
                break
        return papers[:max_results]
