"""
Deduplication by DOI and by fuzzy title.

Nothing is thrown away silently: duplicates are *merged* (sources, provenance,
missing fields) into the record that is kept, and the caller gets counts for
the PRISMA flow.
"""
from difflib import SequenceMatcher

from src.utils.records import get_doi, norm_title

TITLE_THRESHOLD = 0.92


def _richness(p: dict) -> tuple:
    """Prefer the record with abstract, DOI and more citations."""
    return (bool(p.get("abstract")), bool(get_doi(p)), p.get("citationCount") or 0)


def merge_records(a: dict, b: dict) -> dict:
    """Merge two records describing the same paper; keeps the richer one as base."""
    base, other = (a, b) if _richness(a) >= _richness(b) else (b, a)
    merged = dict(base)
    for field in ("abstract", "venue", "year", "openAccessPdf"):
        if not merged.get(field) and other.get(field):
            merged[field] = other[field]
    if not merged.get("authors") and other.get("authors"):
        merged["authors"] = other["authors"]
    if merged.get("publicationType") in (None, "other") and other.get("publicationType") not in (None, "other"):
        merged["publicationType"] = other["publicationType"]
    if not get_doi(merged) and get_doi(other):
        merged["externalIds"] = {"DOI": get_doi(other)}
    cites = [c for c in (a.get("citationCount"), b.get("citationCount")) if c is not None]
    merged["citationCount"] = max(cites) if cites else None
    merged["_sources"] = list(dict.fromkeys((a.get("_sources") or []) + (b.get("_sources") or [])))
    merged["found_in"] = (a.get("found_in") or []) + [
        f for f in (b.get("found_in") or []) if f not in (a.get("found_in") or [])
    ]
    return merged


def _similar(t1: str, w1: set, t2: str, w2: set, threshold: float) -> bool:
    if not t1 or not t2:
        return False
    if t1 == t2:
        return True
    union = w1 | w2
    if not union or len(w1 & w2) / len(union) < threshold * 0.55:
        return False
    return SequenceMatcher(None, t1, t2).ratio() >= threshold


class _TitleIndex:
    """Exact normalized-title lookup plus a fuzzy fallback with a Jaccard pre-filter."""

    def __init__(self):
        self.exact: dict[str, int] = {}
        self.items: list[tuple[str, set, int]] = []

    def add(self, title: str, idx: int):
        t = norm_title(title)
        if not t:
            return
        self.exact.setdefault(t, idx)
        self.items.append((t, set(t.split()), idx))

    def find(self, title: str, threshold: float) -> int | None:
        t = norm_title(title)
        if not t:
            return None
        if t in self.exact:
            return self.exact[t]
        words = set(t.split())
        for t2, w2, idx in self.items:
            if _similar(t, words, t2, w2, threshold):
                return idx
        return None


def dedupe_batch(papers: list[dict], threshold: float = TITLE_THRESHOLD) -> tuple[list[dict], int]:
    """Merge duplicates inside one batch (same DOI or near-identical title)."""
    kept: list[dict] = []
    by_doi: dict[str, int] = {}
    titles = _TitleIndex()
    removed = 0
    for p in papers:
        doi = get_doi(p)
        idx = by_doi.get(doi) if doi else None
        if idx is None:
            idx = titles.find(p.get("title"), threshold)
            # Two different DOIs with the same title are usually preprint vs. published: merge.
        if idx is None:
            kept.append(p)
            i = len(kept) - 1
            if doi:
                by_doi[doi] = i
            titles.add(p.get("title"), i)
        else:
            kept[idx] = merge_records(kept[idx], p)
            removed += 1
            if doi:
                by_doi.setdefault(doi, idx)
    return kept, removed


def match_library(
    papers: list[dict], library: list[dict], threshold: float = TITLE_THRESHOLD
) -> tuple[list[dict], list[tuple[dict, int]]]:
    """Split papers into (new, [(paper, index_in_library), ...])."""
    by_doi = {get_doi(p): i for i, p in enumerate(library) if get_doi(p)}
    by_id = {p.get("id"): i for i, p in enumerate(library)}
    titles = _TitleIndex()
    for i, p in enumerate(library):
        titles.add(p.get("title"), i)

    new, matched = [], []
    for p in papers:
        doi = get_doi(p)
        idx = by_doi.get(doi) if doi else None
        if idx is None:
            idx = by_id.get(p.get("id"))
        if idx is None:
            idx = titles.find(p.get("title"), threshold)
        if idx is None:
            new.append(p)
        else:
            matched.append((p, idx))
    return new, matched
