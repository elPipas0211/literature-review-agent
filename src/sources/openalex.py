"""
OpenAlex Works API client: keyword search, citation snowballing and yearly trends.

Free, no key. Abstracts arrive as inverted indexes and are rebuilt to plain
text. Adding an email (config.yaml -> sources.openalex.email) puts requests in
the faster "polite pool".
"""
import logging
import time
from typing import Callable, Optional

import requests

from src.utils.records import classify_publication_type, detect_review, normalize_doi

logger = logging.getLogger(__name__)

BASE_URL = "https://api.openalex.org/works"
_SELECT = ("id,title,abstract_inverted_index,publication_year,cited_by_count,doi,"
           "authorships,primary_location,type,open_access,referenced_works_count")
_RETRY_STATUS = {429, 500, 502, 503, 504}


def short_id(openalex_id: str | None) -> str | None:
    """'https://openalex.org/W123' -> 'W123'."""
    return openalex_id.rsplit("/", 1)[-1] if openalex_id else None


def _reconstruct_abstract(inverted_index: dict | None) -> str:
    if not inverted_index:
        return ""
    positions = {pos: word for word, locs in inverted_index.items() for pos in locs}
    return " ".join(positions[i] for i in sorted(positions))


def _normalize(work: dict) -> dict:
    doi = normalize_doi(work.get("doi"))
    source = (work.get("primary_location") or {}).get("source") or {}
    title = work.get("title") or ""
    return {
        "title": title,
        "abstract": _reconstruct_abstract(work.get("abstract_inverted_index")),
        "year": work.get("publication_year"),
        "citationCount": work.get("cited_by_count"),
        "externalIds": {"DOI": doi} if doi else {},
        "openalexId": short_id(work.get("id")),
        "authors": [
            {"name": (a.get("author") or {}).get("display_name", "")}
            for a in (work.get("authorships") or []) if (a.get("author") or {}).get("display_name")
        ],
        "venue": source.get("display_name") or "",
        # OpenAlex labels conference papers as type "article"; the source type tells them apart.
        "publicationType": classify_publication_type(source.get("type"), work.get("type")),
        "is_review": detect_review(title, work.get("type")),
        "openAccessPdf": (work.get("open_access") or {}).get("oa_url"),
        "_source": "openalex",
    }


class OpenAlexClient:
    def __init__(self, email: Optional[str] = None, rate_limit_delay: float = 0.15,
                 on_wait: Callable[[str], None] | None = None):
        self._session = requests.Session()
        self._email = email
        self._delay = rate_limit_delay
        self._on_wait = on_wait or (lambda msg: None)

    def _get(self, url: str, params: dict) -> dict:
        params = dict(params)
        if self._email:
            params["mailto"] = self._email
        wait = 2.0
        for attempt in range(5):
            resp = self._session.get(url, params=params, timeout=30)
            if resp.status_code not in _RETRY_STATUS:
                resp.raise_for_status()
                time.sleep(self._delay)
                return resp.json()
            self._on_wait(f"OpenAlex HTTP {resp.status_code}, retrying in {wait:.0f}s")
            time.sleep(wait)
            wait *= 2
        resp.raise_for_status()
        return {}

    def _paginate(self, params: dict, max_results: int) -> list[dict]:
        papers: list[dict] = []
        cursor = "*"
        while len(papers) < max_results and cursor:
            per_page = min(200, max_results - len(papers))
            data = self._get(BASE_URL, {**params, "select": _SELECT, "per_page": per_page, "cursor": cursor})
            batch = data.get("results") or []
            if not batch:
                break
            papers.extend(_normalize(w) for w in batch)
            cursor = (data.get("meta") or {}).get("next_cursor")
        return papers[:max_results]

    # ── keyword search ──────────────────────────────────────────────────────
    def search_all(self, query: str, max_results: int = 100,
                   year_from: int | None = None, year_to: int | None = None) -> list[dict]:
        params = {"search": query}
        if year_from or year_to:
            params["filter"] = f"publication_year:{year_from or ''}-{year_to or ''}"
        return self._paginate(params, max_results)

    # ── snowballing ─────────────────────────────────────────────────────────
    def find_work_id(self, doi: str | None = None, title: str | None = None) -> str | None:
        """Resolve an OpenAlex id from a DOI (exact) or, failing that, the title."""
        if doi:
            try:
                return short_id(self._get(f"{BASE_URL}/doi:{doi}", {"select": "id"}).get("id"))
            except requests.HTTPError:
                pass
        if title:
            data = self._get(BASE_URL, {"filter": f"title.search:{title[:200]}", "per_page": 1, "select": "id"})
            results = data.get("results") or []
            return short_id(results[0]["id"]) if results else None
        return None

    def references(self, work_id: str, max_results: int = 200) -> list[dict]:
        """Backward snowballing: works cited by `work_id`."""
        ids = [short_id(w) for w in (self._get(f"{BASE_URL}/{work_id}", {"select": "referenced_works"})
                                     .get("referenced_works") or [])][:max_results]
        papers: list[dict] = []
        for i in range(0, len(ids), 50):  # OR-filter accepts up to 100 values; 50 keeps URLs short
            chunk = "|".join(ids[i:i + 50])
            papers.extend(self._paginate({"filter": f"openalex_id:{chunk}"}, 50))
        return papers

    def citing(self, work_id: str, max_results: int = 200) -> list[dict]:
        """Forward snowballing: works that cite `work_id`, most cited first."""
        return self._paginate({"filter": f"cites:{work_id}", "sort": "cited_by_count:desc"}, max_results)

    # ── trends ──────────────────────────────────────────────────────────────
    def yearly_counts(self, query: str, year_from: int | None = None,
                      year_to: int | None = None) -> list[dict]:
        """
        Works per publication year whose title or abstract match `query` (all words;
        wrap a phrase in double quotes for an exact match), across all of OpenAlex.
        """
        filters = [f"title_and_abstract.search:{query.replace(',', ' ')}"]
        if year_from or year_to:
            filters.append(f"publication_year:{year_from or ''}-{year_to or ''}")
        params = {"filter": ",".join(filters), "group_by": "publication_year"}
        data = self._get(BASE_URL, params)
        out = [{"year": int(g["key"]), "count": g["count"]}
               for g in data.get("group_by") or [] if str(g.get("key", "")).isdigit()]
        return sorted(out, key=lambda r: r["year"])
