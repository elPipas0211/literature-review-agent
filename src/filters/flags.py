"""
Quality flags. These used to be hard filters that silently deleted papers;
now they only *label* records so you can decide during screening (and report
them in PRISMA if you choose to exclude on that basis).
"""


def _min_citations(year: int | None, floors: dict) -> int:
    if year is None:
        return 0
    pre = floors.get("pre_2015") or {}
    if pre and year < pre.get("year_cutoff", 2015):
        return pre.get("min_citations", 0)
    mid = floors.get("mid_range") or {}
    if mid and mid.get("year_from", 2015) <= year <= mid.get("year_to", 2020):
        return mid.get("min_citations", 0)
    return 0


def compute_flags(paper: dict, floors: dict | None = None) -> list[str]:
    flags = []
    if not (paper.get("abstract") or "").strip():
        flags.append("missing_abstract")
    if not (paper.get("externalIds") or {}).get("DOI"):
        flags.append("missing_doi")
    if paper.get("citationCount") is None:
        flags.append("missing_citation_count")
    floors = floors or {}
    if floors.get("enabled"):
        need = _min_citations(paper.get("year"), floors)
        if (paper.get("citationCount") or 0) < need:
            flags.append("below_citation_floor")
    return flags
