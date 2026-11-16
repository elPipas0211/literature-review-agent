"""
Parse CSV / tab-delimited exports from Scopus, Web of Science or Zotero into
records. Single implementation shared by the API and the CLI.
"""
import csv
import io
import re
from pathlib import Path

from src.utils.records import classify_publication_type, detect_review, normalize_doi

csv.field_size_limit(10_000_000)

COLUMNS = {
    "scopus": {
        "title": ["Title"], "abstract": ["Abstract"], "doi": ["DOI"], "year": ["Year"],
        "citations": ["Cited by"], "authors_full": ["Author full names"], "authors": ["Authors"],
        "venue": ["Source title"], "type": ["Document Type"],
    },
    "wos": {
        "title": ["Article Title", "TI", "Title"], "abstract": ["Abstract", "AB"], "doi": ["DOI", "DI"],
        "year": ["Publication Year", "Year Published", "PY", "Year"],
        "citations": ["Times Cited, All Databases", "Z9", "Times Cited, WoS Core", "TC"],
        "authors_full": ["Author Full Names", "AF"], "authors": ["Authors", "AU"],
        "venue": ["Source Title", "SO", "Full Journal Title"], "type": ["Document Type", "DT"],
    },
    "zotero": {
        "title": ["Title"], "abstract": ["Abstract Note", "Abstract"], "doi": ["DOI"],
        "year": ["Publication Year", "Year"], "citations": [], "authors_full": [],
        "authors": ["Author", "Authors"], "venue": ["Publication Title", "Venue"],
        "type": ["Item Type", "Type"],
    },
}


def _read(path: Path) -> list[dict]:
    raw = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            raw = path.read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    if raw is None:
        raise ValueError("Cannot decode the file (tried UTF-8, CP1252, Latin-1).")
    first = next((ln for ln in raw.splitlines() if ln.strip()), "")
    sep = "\t" if first.count("\t") > first.count(",") else ","
    reader = csv.DictReader(io.StringIO(raw), delimiter=sep)
    return [r for r in reader if any(v and str(v).strip() for v in r.values() if isinstance(v, str))]


def detect_format(columns) -> str:
    cols = {(c or "").lower().strip() for c in columns}
    scores = {
        "scopus": ("eid" in cols) * 3 + ("cited by" in cols) * 2 + ("source title" in cols),
        "wos": ("ut (unique wos id)" in cols) * 3 + ("ut" in cols and "so" in cols) * 3
               + ("times cited, all databases" in cols) * 2 + ("article title" in cols) * 2,
        "zotero": ("item type" in cols) * 3 + ("abstract note" in cols) * 2 + ("publication title" in cols),
    }
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        if "title" in cols:
            return "zotero"  # generic: Title / Abstract / DOI columns
        raise ValueError(
            "Cannot recognise the CSV format. Expected a Scopus, Web of Science or Zotero export "
            f"(first columns found: {sorted(cols)[:12]})."
        )
    return best


def _get(row: dict, candidates: list[str]) -> str:
    lower = {(k or "").lower().strip(): (v or "").strip() for k, v in row.items() if isinstance(v, str)}
    for c in candidates:
        v = lower.get(c.lower(), "")
        if v and v.lower() not in {"nan", "[no abstract available]"}:
            return v
    return ""


def _int(s: str) -> int | None:
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def parse_authors(full: str, short: str, fmt: str) -> list[dict]:
    """Prefer full names ("Smith, John (123)") over abbreviated ones ("Smith J.")."""
    raw = full or short
    if not raw:
        return []
    if ";" in raw:
        parts = raw.split(";")
    elif fmt == "scopus" and not full:
        parts = raw.split(", ")  # old Scopus exports: "Smith J., Doe A."
    else:
        parts = [raw]
    names = []
    for p in parts:
        p = re.sub(r"\s*\(\d+\)\s*$", "", p).strip()  # drop Scopus author ids
        if not p:
            continue
        if fmt == "wos" and p.isupper() and len(p) > 3:
            p = p.title()
        names.append({"name": p})
    return names


def parse_csv(path: str | Path) -> tuple[str, int, list[dict]]:
    """Return (format, n_rows, records)."""
    rows = _read(Path(path))
    if not rows:
        raise ValueError("The file has no data rows.")
    fmt = detect_format(rows[0].keys())
    cmap = COLUMNS[fmt]
    records = []
    for row in rows:
        title = _get(row, cmap["title"])
        if not title:
            continue
        doi = normalize_doi(_get(row, cmap["doi"]))
        doc_type = _get(row, cmap["type"])
        records.append({
            "is_review": detect_review(title, doc_type),
            "title": title,
            "abstract": _get(row, cmap["abstract"]),
            "externalIds": {"DOI": doi} if doi else {},
            "year": _int(_get(row, cmap["year"])),
            "citationCount": _int(_get(row, cmap["citations"])) if cmap["citations"] else None,
            "authors": parse_authors(_get(row, cmap["authors_full"]), _get(row, cmap["authors"]), fmt),
            "venue": _get(row, cmap["venue"]),
            "publicationType": classify_publication_type(doc_type),
            "openAccessPdf": None,
            "_source": f"{fmt}_csv",
        })
    return fmt, len(rows), records
