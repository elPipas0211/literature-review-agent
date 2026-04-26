"""
BibTeX exporter.

Generates one @article entry per paper. Cite keys follow the convention
LastnameYear_doitag (e.g. Smith2022_10.1145) so they remain stable as long
as the DOI doesn't change, and are human-readable enough for manual editing.
"""
import re
from pathlib import Path


def _safe_key(s: str) -> str:
    """Strip characters that BibTeX cite keys don't allow."""
    return re.sub(r"[^a-zA-Z0-9_:.-]", "", s)


def _escape(value: str) -> str:
    """Replace curly braces with parentheses to prevent unbalanced-brace errors in BibTeX parsers."""
    return value.replace("\\", "").replace("{", "(").replace("}", ")")


def _cite_key(paper: dict) -> str:
    """Build a human-readable, stable cite key from the first author's last name, year, and DOI."""
    authors = paper.get("authors") or []
    first_author = (authors[0].get("name") or "") if authors else ""
    last_name = first_author.strip().split()[-1] if first_author.strip() else "Unknown"
    year = str(paper.get("year") or "0000")
    doi = ((paper.get("externalIds") or {}).get("DOI") or "")
    # use last segment of DOI for readability
    doi_tag = doi.split("/")[-1][:10] if "/" in doi else doi[:10]
    return _safe_key(f"{last_name}{year}_{doi_tag}") or f"paper{year}"


def _authors_str(paper: dict) -> str:
    """Format the author list as 'Name1 and Name2 and ...' as BibTeX requires."""
    names = [a.get("name", "") for a in (paper.get("authors") or []) if a.get("name")]
    return " and ".join(names) if names else "Unknown"


def paper_to_bibtex(paper: dict) -> str:
    """Convert one paper dict to a single BibTeX @article entry string."""
    key = _cite_key(paper)
    doi = ((paper.get("externalIds") or {}).get("DOI") or "").strip()
    title = _escape((paper.get("title") or "").strip())
    abstract = _escape((paper.get("abstract") or "").strip())
    venue = _escape((paper.get("venue") or "").strip())
    year = str(paper.get("year") or "")
    authors = _authors_str(paper)
    cites = paper.get("citationCount")

    ev = paper.get("evaluation") or {}
    category = ev.get("category", "")

    fields = [
        ("title", title),
        ("author", authors),
    ]
    if year:
        fields.append(("year", year))
    if venue:
        fields.append(("journal", venue))
    if doi:
        fields.append(("doi", doi))
    if abstract:
        fields.append(("abstract", abstract))

    note_parts = []
    if cites is not None:
        note_parts.append(f"Citations: {cites}")
    if category:
        note_parts.append(f"Category: {category}")
    if note_parts:
        fields.append(("note", "; ".join(note_parts)))

    lines = [f"@article{{{key},"]
    for name, value in fields:
        lines.append(f"  {name:<10} = {{{value}}},")
    lines.append("}")
    return "\n".join(lines)


def export_bibtex(papers: list[dict], out_path: str | Path) -> int:
    """Write BibTeX file with all papers. Returns number of entries written."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    entries = [paper_to_bibtex(p) for p in papers]
    out_path.write_text("\n\n".join(entries) + "\n", encoding="utf-8")
    return len(entries)
