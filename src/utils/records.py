"""
Helpers shared by every stage that touches a paper record.

A *record* is a plain dict with (at least) these keys:

    id               stable key: normalized DOI, or "noDOI_<hash of title+year>"
    title, abstract, year, citationCount, venue
    externalIds      {"DOI": "<normalized doi>"}  (empty dict when unknown)
    authors          [{"name": "..."}]
    publicationType  article | conference | chapter | book | preprint | thesis | other
    openAccessPdf    URL string or None
    openalexId       "W123..." when known (needed for snowballing)
    is_review        survey / review article (document type or title wording)
    keywords         KeyBERT keyphrases (computed once per paper)
    starred, note    your reading list — never overwritten by later searches
    _sources         list of sources that returned it (openalex, scopus_csv, snowball, ...)
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


_MINOR = {"a", "an", "and", "as", "at", "but", "by", "for", "from", "in", "into", "nor", "of", "on",
          "or", "over", "the", "to", "via", "with", "de", "del", "la", "le", "et", "und", "y", "e"}
_ACRONYMS = {"IEEE", "ACM", "IET", "SIAM", "IFIP", "AAAI", "ACL", "IJCAI", "IJCNN", "NIPS", "NEURIPS",
             "ICML", "ICLR", "KDD", "SIGKDD", "SIGCOMM", "USENIX", "IOT", "AI", "ML", "NLP", "IT", "ICT",
             "USA", "UK", "EU", "MDPI", "PLOS", "BMC", "SPIE", "IAENG", "WSEAS", "CEUR", "LNCS", "AMIA",
             "ICCCS", "ICT", "ISA", "IEICE", "JMLR", "PMLR", "ICC", "GLOBECOM", "INFOCOM", "CCS", "NDSS"}


def unshout(text: str | None) -> str:
    """'JOURNAL OF NETWORK SECURITY' -> 'Journal of Network Security' (Web of Science writes
    venue names in capitals). Mixed-case text is returned unchanged."""
    text = (text or "").strip()
    letters = [c for c in text if c.isalpha()]
    if not letters or not all(c.isupper() for c in letters) or len(letters) < 6:
        return text
    out = []
    for i, word in enumerate(text.split()):
        core = word.strip("()[],.:;&-")
        if (core.upper() in _ACRONYMS or any(c.isdigit() for c in core)
                or (word.startswith("(") and word.rstrip(".,;:").endswith(")"))):   # (COLCOM), (ICCCS)
            out.append(word)
        elif i > 0 and core.lower() in _MINOR:
            out.append(word.lower())
        else:
            out.append("-".join(p[:1].upper() + p[1:].lower() for p in word.split("-")))
    return " ".join(out)


def page_range(first, last=None) -> str:
    """'100', '110' -> '100-110'; keeps a single page or an article number as is."""
    first, last = str(first or "").strip(), str(last or "").strip()
    if first and last and last != first:
        return f"{first}-{last}"
    return first


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


_REVIEW_TITLE = re.compile(
    r"\b(survey|review|overview|state[- ]of[- ]the[- ]art|meta[- ]analysis|systematic mapping|"
    r"scoping study|literature analysis|tutorial)\b", re.IGNORECASE)


def detect_review(title: str | None, *type_hints: str | None) -> bool:
    """Surveys / reviews: from the source's document type or the title wording."""
    if any(h and "review" in h.lower() for h in type_hints):
        return True
    return bool(_REVIEW_TITLE.search(title or ""))


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
    p.setdefault("openalexId", None)
    if "is_review" not in p:
        p["is_review"] = detect_review(p["title"])
    p["id"] = paper_key(p)
    return p
