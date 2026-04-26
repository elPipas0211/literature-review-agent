"""
Semantic Scholar API client.

Uses the public Graph API v1 — no key required, but an optional API key raises
the rate limit from ~100 requests/5 min to a much higher tier. The key is passed
as a header (x-api-key) so it never appears in URLs or server logs.
"""
import logging
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_FIELDS = (
    "title,abstract,year,citationCount,externalIds,"
    "authors,venue,publicationTypes,openAccessPdf"
)


class SemanticScholarClient:
    """Thin wrapper around the Semantic Scholar Graph API v1 paper search endpoint."""

    BASE_URL = "https://api.semanticscholar.org/graph/v1"

    def __init__(self, api_key: Optional[str] = None, rate_limit_delay: float = 1.0):
        self._session = requests.Session()
        if api_key:
            self._session.headers["x-api-key"] = api_key
        self._delay = rate_limit_delay

    def _get(self, endpoint: str, params: dict) -> dict:
        """Make a single GET request and sleep afterward to respect rate limits."""
        url = f"{self.BASE_URL}/{endpoint}"
        response = self._session.get(url, params=params, timeout=30)
        response.raise_for_status()
        time.sleep(self._delay)
        return response.json()

    def search(self, query: str, limit: int = 100, offset: int = 0) -> dict:
        """Fetch one page of results (up to 100 papers per page, as the API allows)."""
        return self._get("paper/search", {
            "query": query,
            "fields": _FIELDS,
            "limit": min(limit, 100),
            "offset": offset,
        })

    def search_all(self, query: str, max_results: int = 100) -> list[dict]:
        """Paginate through results up to max_results."""
        papers: list[dict] = []
        batch_size = min(100, max_results)
        offset = 0

        while len(papers) < max_results:
            data = self.search(query, limit=batch_size, offset=offset)
            batch = data.get("data", [])
            if not batch:
                break
            papers.extend(batch)
            logger.debug(f"Fetched {len(papers)} papers so far (offset={offset})")
            offset += len(batch)
            if len(batch) < batch_size:
                break

        return papers[:max_results]
