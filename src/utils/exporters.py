"""
CSV and RIS exports for screening / reference tools.

  * CSV: opens in Excel (UTF-8 with BOM) and is accepted by ASReview and Rayyan
    (columns title, abstract, authors, year, doi ...).
  * RIS: imports into Zotero, Mendeley, EndNote, Rayyan and ASReview.
"""
import csv
import io

_RIS_TYPES = {"article": "JOUR", "conference": "CONF", "chapter": "CHAP", "book": "BOOK",
              "thesis": "THES", "preprint": "UNPB", "other": "GEN"}

CSV_COLUMNS = ["id", "title", "abstract", "authors", "year", "venue", "doi", "url",
               "publication_type", "citations", "similarity", "semantic_score", "score",
               "category", "is_review", "starred", "validation", "note", "keywords", "flags", "sources", "queries"]


def _row(p: dict) -> dict:
    ev = p.get("evaluation") or {}
    doi = (p.get("externalIds") or {}).get("DOI") or ""
    return {
        "id": p.get("id"),
        "title": p.get("title") or "",
        "abstract": p.get("abstract") or "",
        "authors": "; ".join(a.get("name", "") for a in p.get("authors") or []),
        "year": p.get("year") or "",
        "venue": p.get("venue") or "",
        "doi": doi,
        "url": p.get("openAccessPdf") or (f"https://doi.org/{doi}" if doi else ""),
        "publication_type": p.get("publicationType") or "",
        "citations": "" if p.get("citationCount") is None else p["citationCount"],
        "similarity": ev.get("similarity", ""),
        "semantic_score": ev.get("semantic_score", ""),
        "score": ev.get("score", ""),
        "category": ev.get("category", "unevaluated"),
        "is_review": "yes" if p.get("is_review") else "",
        "starred": "yes" if p.get("starred") else "",
        "validation": p.get("validation") or "",
        "note": p.get("note") or "",
        "keywords": "; ".join(p.get("keywords") or []),
        "flags": "; ".join(p.get("flags") or []),
        "sources": "; ".join(p.get("_sources") or []),
        "queries": " | ".join(dict.fromkeys(f.get("query") or "" for f in p.get("found_in") or [])),
    }


def to_csv(papers: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for p in papers:
        writer.writerow(_row(p))
    return "﻿" + buf.getvalue()


def to_ris(papers: list[dict]) -> str:
    out = []
    for p in papers:
        ev = p.get("evaluation") or {}
        lines = [f"TY  - {_RIS_TYPES.get(p.get('publicationType') or 'other', 'GEN')}",
                 f"TI  - {(p.get('title') or '').strip()}"]
        lines += [f"AU  - {a['name']}" for a in p.get("authors") or [] if a.get("name")]
        if p.get("year"):
            lines.append(f"PY  - {p['year']}")
        if p.get("venue"):
            lines.append(f"T2  - {p['venue']}")
        doi = (p.get("externalIds") or {}).get("DOI")
        if doi:
            lines.append(f"DO  - {doi}")
        if p.get("openAccessPdf"):
            lines.append(f"UR  - {p['openAccessPdf']}")
        if p.get("abstract"):
            lines.append(f"AB  - {' '.join(p['abstract'].split())}")
        lines += [f"KW  - {k}" for k in p.get("keywords") or []]
        note = []
        if p.get("note"):
            note.append(p["note"])
        if p.get("starred"):
            note.append("starred")
        if p.get("is_review"):
            note.append("review/survey")
        if ev:
            note.append(f"score={ev.get('score')} category={ev.get('category')}")
        if p.get("citationCount") is not None:
            note.append(f"citations={p['citationCount']}")
        if p.get("flags"):
            note.append("flags=" + ",".join(p["flags"]))
        if note:
            lines.append("N1  - " + "; ".join(note))
        lines.append("ER  - ")
        out.append("\n".join(lines))
    return "\n\n".join(out) + "\n"
