"""
Deduplication utilities: by DOI and by title similarity.

When the same DOI appears in both Semantic Scholar and OpenAlex, the first
occurrence (SS, which appears first in the clients list) is kept and the
'_sources' list is extended to track all origins.

Papers without a DOI are never deduplicated by DOI — they're always kept as-is.
"""
from difflib import SequenceMatcher


def _norm_title(title: str) -> str:
    """Lowercase and collapse whitespace so title comparisons are case- and spacing-insensitive."""
    return " ".join(title.lower().split())


def deduplicate_by_doi(papers: list[dict]) -> tuple[list[dict], int]:
    """
    Return (unique_papers, n_duplicates_removed).
    unique_papers preserves original insertion order for DOI-less papers.
    """
    seen: dict[str, dict] = {}
    no_doi: list[dict] = []
    duplicates = 0

    for paper in papers:
        doi = ((paper.get("externalIds") or {}).get("DOI") or "").strip().lower()
        if not doi:
            no_doi.append(paper)
            continue

        if doi in seen:
            duplicates += 1
            existing = seen[doi]
            sources = existing.get("_sources", [existing.get("_source", "unknown")])
            new_src = paper.get("_source", "unknown")
            if new_src not in sources:
                sources.append(new_src)
            existing["_sources"] = sources
        else:
            p = dict(paper)
            p["_sources"] = [p.get("_source", "unknown")]
            seen[doi] = p

    return list(seen.values()) + no_doi, duplicates


def deduplicate_by_title(
    papers: list[dict],
    threshold: float = 0.90,
) -> tuple[list[dict], int]:
    """
    Remove near-duplicate titles within a batch.

    When two papers share a title with SequenceMatcher ratio >= threshold,
    keep the one with more citations. Papers with empty titles are never
    deduplicated. Returns (unique_papers, n_removed).
    """
    kept: list[dict] = []
    removed = 0

    for paper in papers:
        raw = (paper.get("title") or "").strip()
        if not raw:
            kept.append(paper)
            continue
        norm = _norm_title(raw)
        words = set(norm.split())

        match_idx: int | None = None
        for i, existing in enumerate(kept):
            e_norm = _norm_title((existing.get("title") or "").strip())
            if not e_norm:
                continue
            # Quick word-overlap pre-filter before the expensive SequenceMatcher call
            e_words = set(e_norm.split())
            union = words | e_words
            if union and len(words & e_words) / len(union) < threshold * 0.55:
                continue
            if SequenceMatcher(None, norm, e_norm).ratio() >= threshold:
                match_idx = i
                break

        if match_idx is None:
            kept.append(paper)
        else:
            new_cites = paper.get("citationCount") or 0
            existing_cites = kept[match_idx].get("citationCount") or 0
            if new_cites > existing_cites:
                kept[match_idx] = paper
            removed += 1

    return kept, removed


def filter_known_by_title(
    papers: list[dict],
    master_titles: list[str],
    threshold: float = 0.90,
) -> tuple[list[dict], int]:
    """
    Remove papers whose title is too similar to any title already in master_db.

    Papers with empty titles are never filtered. Uses a Jaccard word-overlap
    pre-filter to avoid expensive SequenceMatcher calls on dissimilar pairs.
    Returns (new_papers, n_skipped).
    """
    master_norms = [_norm_title(t) for t in master_titles if t.strip()]
    master_words = [set(n.split()) for n in master_norms]
    jaccard_floor = threshold * 0.55

    new: list[dict] = []
    skipped = 0

    for paper in papers:
        raw = (paper.get("title") or "").strip()
        if not raw:
            new.append(paper)
            continue
        norm = _norm_title(raw)
        words = set(norm.split())

        is_dup = False
        for mt, mt_words in zip(master_norms, master_words):
            union = words | mt_words
            if not union:
                continue
            if len(words & mt_words) / len(union) < jaccard_floor:
                continue
            if SequenceMatcher(None, norm, mt).ratio() >= threshold:
                is_dup = True
                break

        if is_dup:
            skipped += 1
        else:
            new.append(paper)

    return new, skipped
