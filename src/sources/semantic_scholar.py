"""
Semantic Scholar Graph API client.

Without an API key the shared public pool answers HTTP 429 very often, so
every request retries with exponential backoff (honouring Retry-After).
Get a free key at https://www.semanticscholar.org/product/api and put it in
config.yaml -> sources.semantic_scholar.api_key.
"""
import logging
import time
from typing import Callable, Optional

import requests

from src.utils.records import classify_publication_type

logger = logging.getLogger(__name__)

BASE_URL = "https://api.semanticscholar.org/graph/v1"
_FIELDS = "title,abstract,year,citationCount,externalIds,authors,venue,publicationTypes,openAccessPdf"
_RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_OFFSET = 1000  # the relevance-search endpoint never returns past offset 1000


class SemanticScholarError(RuntimeError):
    pass


def _normalize(p: dict) -> dict:
    ext = p.get("externalIds") or {}
    types = p.get("publicationTypes") or []
    hint = " ".join(types)
    if not hint and ext.get("ArXiv") and not ext.get("DOI"):
        hint = "preprint"
    return {
        "title": p.get("title") or "",
        "abstract": p.get("abstract") or "",
        "year": p.get("year"),
        "citationCount": p.get("citationCount"),
        "externalIds": {"DOI": ext.get("DOI")} if ext.get("DOI") else {},
        "authors": [{"name": a.get("name", "")} for a in (p.get("authors") or []) if a.get("name")],
        "venue": p.get("venue") or "",
        "publicationType": classify_publication_type(hint) if hint else ("article" if p.get("venue") else "other"),
        "openAccessPdf": ((p.get("openAccessPdf") or {}).get("url")) or None,
        "_source": "semantic_scholar",
    }


class SemanticScholarClient:
    def __init__(self, api_key: Optional[str] = None, rate_limit_delay: float = 1.0,
                 max_retries: int = 5, on_wait: Callable[[str], None] | None = None):
        self._session = requests.Session()
        if api_key:
            self._session.headers["x-api-key"] = api_key
        self._has_key = bool(api_key)
        self._delay = rate_limit_delay
        self._max_retries = max_retries
        self._on_wait = on_wait or (lambda msg: None)

    def _get(self, endpoint: str, params: dict) -> dict:
        url = f"{BASE_URL}/{endpoint}"
        wait = 2.0
        for attempt in range(self._max_retries + 1):
            resp = self._session.get(url, params=params, timeout=30)
            if resp.status_code not in _RETRY_STATUS:
                resp.raise_for_status()
                time.sleep(self._delay)
                return resp.json()
            if attempt == self._max_retries:
                break
            retry_after = resp.headers.get("Retry-After")
            delay = float(retry_after) if retry_after and retry_after.isdigit() else wait
            self._on_wait(f"Semantic Scholar HTTP {resp.status_code}, retrying in {delay:.0f}s "
                          f"({attempt + 1}/{self._max_retries})")
            time.sleep(delay)
            wait = min(wait * 2, 30)
        hint = "" if self._has_key else " Add a free API key in config.yaml (sources.semantic_scholar.api_key)."
        raise SemanticScholarError(f"Semantic Scholar kept answering HTTP {resp.status_code}.{hint}")

    def search_all(self, query: str, max_results: int = 100,
                   year_from: int | None = None, year_to: int | None = None) -> list[dict]:
        papers: list[dict] = []
        max_results = min(max_results, MAX_OFFSET)
        offset = 0
        params = {"query": query, "fields": _FIELDS}
        if year_from or year_to:
            params["year"] = f"{year_from or ''}-{year_to or ''}"
        while len(papers) < max_results:
            limit = min(100, max_results - len(papers))
            data = self._get("paper/search", {**params, "limit": limit, "offset": offset})
            batch = data.get("data") or []
            papers.extend(_normalize(p) for p in batch)
            offset += len(batch)
            if len(batch) < limit or data.get("next") is None:
                break
        return papers[:max_results]
