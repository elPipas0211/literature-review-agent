"""
BibTeX export — the single generator used for master.bib, the download button
and the per-paper "Copy" in the UI, so cite keys always match.

  * Cite keys: lastname + year + first significant title word (Better BibTeX
    style, e.g. `smith2021deep`), ASCII-folded, de-duplicated with a/b/c.
  * Authors are written as "Last, First" so BibTeX never mistakes initials
    for surnames ("Smith J." -> "Smith, J.").
  * LaTeX special characters are escaped; acronyms in titles are brace-protected.
  * Entry type follows the publication type (@article, @inproceedings, ...).
"""
import re
import unicodedata
from pathlib import Path

_INITIALS = re.compile(r"^(?:[A-Z]\.?-?){1,4}$")
_PARTICLES = {"van", "von", "de", "da", "del", "der", "di", "le", "la", "dos", "du", "ten", "ter"}
_STOP = {"a", "an", "the", "on", "of", "in", "for", "and", "to", "with", "towards", "toward",
         "un", "una", "el", "la", "los", "las", "de", "del", "en", "y", "para", "por"}
_LATEX = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
          "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}

_TYPES = {
    "article": ("article", "journal"),
    "conference": ("inproceedings", "booktitle"),
    "chapter": ("incollection", "booktitle"),
    "book": ("book", "publisher"),
    "thesis": ("phdthesis", "school"),
    "preprint": ("misc", "howpublished"),
    "other": ("misc", "howpublished"),
}


def latex_escape(text: str) -> str:
    return "".join(_LATEX.get(c, c) for c in (text or ""))


def _ascii(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in t if not unicodedata.combining(c)).encode("ascii", "ignore").decode()


def split_name(name: str) -> tuple[str, str]:
    """Return (last, first) for 'Last, First', 'Last F.' (Scopus) or 'First Last'."""
    name = " ".join((name or "").split())
    if not name:
        return "", ""
    if "," in name:
        last, first = name.split(",", 1)
        return last.strip(), first.strip()
    tokens = name.split(" ")
    if len(tokens) == 1:
        return tokens[0], ""
    if _INITIALS.match(tokens[-1]):          # "Smith J." / "Garcia-Lopez A.B."
        return " ".join(tokens[:-1]), tokens[-1]
    i = len(tokens) - 1                      # "Ludwig van Beethoven" -> "van Beethoven"
    while i > 1 and tokens[i - 1].lower() in _PARTICLES:
        i -= 1
    return " ".join(tokens[i:]), " ".join(tokens[:i])


def _protect_title(title: str) -> str:
    """Brace-protect acronyms/CamelCase (LSTM, IoT, COVID-19) so styles don't lowercase them."""
    out = []
    for word in (title or "").split():
        m = re.match(r"^(\W*)(.*?)(\W*)$", word)
        lead, core, trail = m.groups()
        # Protect only if some hyphen part has a capital after its first letter (LSTM, IoT,
        # COVID-19); plain Title-Case words like "Self-Supervised" are left alone.
        protect = any(any(c.isupper() for c in part[1:]) for part in core.split("-"))
        core = latex_escape(core)
        out.append(latex_escape(lead) + ("{" + core + "}" if protect else core) + latex_escape(trail))
    return " ".join(out)


def _base_key(paper: dict) -> str:
    authors = paper.get("authors") or []
    last = split_name(authors[0].get("name", ""))[0] if authors else "anon"
    last = re.sub(r"[^a-z]", "", _ascii(last).lower()) or "anon"
    year = str(paper.get("year") or "nd")
    words = [re.sub(r"[^a-z0-9]", "", w) for w in _ascii(paper.get("title") or "").lower().split()]
    word = next((w for w in words if w and w not in _STOP), "")
    return f"{last}{year}{word}"


def assign_cite_keys(papers: list[dict]) -> dict[str, str]:
    """Map paper id -> unique cite key. Deterministic for a given library."""
    keys: dict[str, str] = {}
    used: dict[str, int] = {}
    for p in sorted(papers, key=lambda p: p.get("id") or ""):
        base = _base_key(p)
        n = used.get(base, 0)
        used[base] = n + 1
        if n == 0:
            keys[p.get("id")] = base
        else:
            keys[p.get("id")] = f"{base}{chr(ord('a') + n - 1)}" if n <= 26 else f"{base}_{n}"
    return keys


def paper_to_bibtex(paper: dict, key: str) -> str:
    entry_type, venue_field = _TYPES.get(paper.get("publicationType") or "other", _TYPES["other"])
    authors = " and ".join(
        latex_escape(f"{last}, {first}" if first else last)
        for last, first in (split_name(a.get("name", "")) for a in paper.get("authors") or [])
        if last
    )
    doi = (paper.get("externalIds") or {}).get("DOI")
    fields = [("title", _protect_title(paper.get("title") or ""))]
    if authors:
        fields.append(("author", authors))
    if paper.get("year"):
        fields.append(("year", str(paper["year"])))
    if paper.get("venue"):
        fields.append((venue_field, latex_escape(paper["venue"])))
    elif entry_type == "misc" and paper.get("publicationType") == "preprint":
        fields.append(("howpublished", "Preprint"))
    if doi:
        fields.append(("doi", doi))
    if paper.get("openAccessPdf"):
        fields.append(("url", paper["openAccessPdf"]))
    if paper.get("abstract"):
        fields.append(("abstract", latex_escape(paper["abstract"])))
    lines = [f"@{entry_type}{{{key},"]
    lines += [f"  {name:<9} = {{{value}}}," for name, value in fields]
    lines.append("}")
    return "\n".join(lines)


def library_bibtex(papers: list[dict]) -> dict[str, tuple[str, str]]:
    """Map paper id -> (cite_key, bibtex entry)."""
    keys = assign_cite_keys(papers)
    return {p["id"]: (keys[p["id"]], paper_to_bibtex(p, keys[p["id"]])) for p in papers}


def export_bibtex(papers: list[dict], out_path: str | Path | None = None, only_ids=None) -> str:
    """Return the .bib text (keys computed over the whole library) and optionally write it."""
    entries = library_bibtex(papers)
    ids = [p["id"] for p in papers if only_ids is None or p["id"] in only_ids]
    text = "\n\n".join(entries[i][1] for i in ids) + "\n"
    if out_path:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_text(text, encoding="utf-8")
    return text
