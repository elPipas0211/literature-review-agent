"""
Citation floor pre-filter: discard papers that are too old and too low-impact
to be worth sending to Claude.

Design (per user spec):
  - year < 2015  AND  citations < pre_2015.min_citations  → discard
  - 2015 <= year <= 2020  AND  citations < mid_range.min_citations  → discard
  - year > 2020  → no floor (too recent to judge by citations)
  - year unknown → pass through (don't penalise for missing metadata)
"""


def _get_min_citations(year: int | None, floors_cfg: dict) -> int:
    """
    Return the minimum citation threshold for a paper given its publication year.

    Older papers have had more time to accumulate citations, so a higher floor
    is applied to pre-2015 work. Papers with an unknown year or published after
    2020 are passed through unconditionally — recent papers haven't had time to
    be cited yet.
    """
    if year is None:
        return 0
    pre = floors_cfg.get("pre_2015", {})
    if pre and year < pre.get("year_cutoff", 2015):
        return pre.get("min_citations", 0)
    mid = floors_cfg.get("mid_range", {})
    if mid and mid.get("year_from", 2015) <= year <= mid.get("year_to", 2020):
        return mid.get("min_citations", 0)
    return 0


def apply_citation_floor(
    papers: list[dict],
    floors_cfg: dict,
) -> tuple[list[dict], list[dict]]:
    """Return (passed, discarded). Discarded items carry a '_floor_reason' key."""
    passed, discarded = [], []
    for paper in papers:
        year = paper.get("year")
        citations = paper.get("citationCount") or 0
        min_cit = _get_min_citations(year, floors_cfg)
        if citations < min_cit:
            discarded.append({
                **paper,
                "_floor_reason": f"year={year} citations={citations} < floor={min_cit}",
            })
        else:
            passed.append(paper)
    return passed, discarded
