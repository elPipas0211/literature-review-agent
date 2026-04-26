"""
Mechanical pre-filter: discard papers missing abstract, DOI, or citation count.
Returns (passed: bool, reasons: list[str]) so callers can log why a paper was dropped.
"""


def passes_mechanical_filter(
    paper: dict,
    require_abstract: bool = True,
    require_doi: bool = True,
    require_citation_count: bool = True,
) -> tuple[bool, list[str]]:
    """
    Check a single paper against the mandatory metadata requirements.

    Papers without an abstract can't be evaluated semantically. Papers without
    a DOI can't be deduplicated reliably across sources. Papers without a
    citation count can't be scored by impact. All three checks are configurable
    via config.yaml so they can be relaxed for specific workflows (e.g. very new papers).
    """
    reasons: list[str] = []

    if require_abstract and not (paper.get("abstract") or "").strip():
        reasons.append("missing_abstract")

    if require_doi:
        doi = (paper.get("externalIds") or {}).get("DOI")
        if not doi:
            reasons.append("missing_doi")

    if require_citation_count and paper.get("citationCount") is None:
        reasons.append("missing_citation_count")

    return len(reasons) == 0, reasons


def apply_filter(
    papers: list[dict],
    require_abstract: bool = True,
    require_doi: bool = True,
    require_citation_count: bool = True,
) -> tuple[list[dict], list[dict]]:
    """Split papers into (passed, rejected). Rejected items carry a 'filter_reasons' key."""
    passed, rejected = [], []
    for paper in papers:
        ok, reasons = passes_mechanical_filter(
            paper, require_abstract, require_doi, require_citation_count
        )
        if ok:
            passed.append(paper)
        else:
            rejected.append({**paper, "filter_reasons": reasons})
    return passed, rejected
