"""
Helpers shared by every stage that touches a paper record.

A *record* is a plain dict with (at least) these keys:

    id               stable key: normalized DOI, or "noDOI_<hash of title+year>"
    title, abstract, year, citationCount, venue
    externalIds      {"DOI": "<normalized doi>"}  (empty dict when unknown)
    authors          [{"name": "..."}]
    publicationType  article | conference | chapter | book | preprint | thesis | other
    openAccessPdf    URL string or None
    _sources         list of sources that returned it (semantic_scholar, openalex, scopus_csv, ...)
    found_in         list of {"session", "kind", "query", "source"} — provenance for PRISMA-S
    flags            list of quality flags (missing_abstract, missing_doi, ...) — never used to drop
    evaluation       {"similarity", "semantic_score", "impact_score", "score", "category"} or absent
"""
import hashlib
import re
import unicodedata

_DOI_PREFIX = re.compile(r"^\s*(?:https?://)?(?:dx\.)?doi\.org/|^\s*doi:\s*", re.IGNORECASE)


def normalize_doi(raw) -> str | None:
    """Return a lowercase DOI without URL / 'doi:' prefixes, or None."""
    if not raw:
        return None
    doi = str(raw).strip()
    # Apply twice to handle odd inputs like "doi: https://doi.org/10..."
    for _ in range(2):
        doi = _DOI_PREFIX.sub("", doi).strip()
    doi = doi.lower()
    return doi if doi.startswith("10.") else (doi or None)


def get_doi(paper: dict) -> str | None:
    return normalize_doi((paper.get("externalIds") or {}).get("DOI"))


def norm_title(title: str | None) -> str:
    """Lowercase, strip accents and punctuation, collapse whitespace."""
    t = unicodedata.normalize("NFKD", title or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return " ".join(t.split())


def paper_key(paper: dict) -> str:
    doi = get_doi(paper)
    if doi:
        return doi
    raw = f"{norm_title(paper.get('title'))}_{paper.get('year') or ''}"
    return "noDOI_" + hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


def paper_text(paper: dict) -> str:
    """Text used for embeddings: title + abstract."""
    title = (paper.get("title") or "").strip()
    abstract = (paper.get("abstract") or "").strip()
    return f"{title}. {abstract}".strip(" .") if abstract else title


def classify_publication_type(*hints: str | None) -> str:
    """Map source-specific type labels to our small vocabulary."""
    text = " ".join(h for h in hints if h).lower()
    if not text:
        return "other"
    if "conference" in text or "proceeding" in text:
        return "conference"
    if "chapter" in text or "booksection" in text or "book section" in text:
        return "chapter"
    if "preprint" in text or "posted-content" in text or "arxiv" in text:
        return "preprint"
    if "dissertation" in text or "thesis" in text:
        return "thesis"
    if "book" in text:
        return "book"
    if "article" in text or "journal" in text or "review" in text or "letter" in text:
        return "article"
    return "other"


def finalize_record(paper: dict) -> dict:
    """Normalize DOI, assign id, make sure list fields exist."""
    p = dict(paper)
    doi = get_doi(p)
    p["externalIds"] = {"DOI": doi} if doi else {}
    p["title"] = (p.get("title") or "").strip()
    abstract = (p.get("abstract") or "").strip()
    if abstract.lower() in {"[no abstract available]", "no abstract available", "nan"}:
        abstract = ""
    p["abstract"] = abstract
    p.setdefault("authors", [])
    p.setdefault("venue", "")
    p.setdefault("publicationType", "other")
    p.setdefault("openAccessPdf", None)
    p["_sources"] = list(dict.fromkeys(p.get("_sources") or [p.get("_source") or "unknown"]))
    p.pop("_source", None)
    p.setdefault("found_in", [])
    p["id"] = paper_key(p)
    return p
