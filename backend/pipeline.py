"""
Pipeline execution functions that emit structured events for SSE streaming.
Mirrors scripts/search.py and scripts/import_csv.py logic without argparse.
"""
import concurrent.futures
import sys
import tempfile
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.embeddings.chroma_store import MasterVectorDB
from src.evaluation.embedding_evaluator import EmbeddingEvaluator
from src.filters.citation_floor import apply_citation_floor
from src.filters.mechanical import apply_filter
from src.sources.openalex import OpenAlexClient
from src.sources.semantic_scholar import SemanticScholarClient
from src.storage.project_manager import ProjectManager
from src.utils.bibtex_exporter import export_bibtex
from src.utils.deduplication import (
    deduplicate_by_doi,
    deduplicate_by_title,
    filter_known_by_title,
)

Emit = Callable[[dict], None]


# ── Search pipeline ────────────────────────────────────────────────────────────

def _fetch_source(name: str, client, query: str, max_results: int, flt_cfg: dict, pm, session_path, emit: Emit):
    emit({"type": "fetch_start", "source": name})
    raw = client.search_all(query, max_results=max_results)
    passed, rejected = apply_filter(
        raw,
        require_abstract=flt_cfg["require_abstract"],
        require_doi=flt_cfg["require_doi"],
        require_citation_count=flt_cfg["require_citation_count"],
    )
    emit({"type": "fetch_done", "source": name,
          "retrieved": len(raw), "passed": len(passed), "rejected": len(rejected)})
    pm.save_query_results(session_path, query, name, passed, rejected)
    return {"passed": passed, "rejected": rejected}


def run_search(
    project: str,
    query: str,
    context: str | None,
    max_results: int,
    config: dict,
    emit: Emit,
) -> None:
    ss_cfg = config["sources"]["semantic_scholar"]
    oa_cfg = config["sources"]["openalex"]
    flt_cfg = config["filters"]
    floor_cfg = config["citation_floors"]
    emb_model = config["embeddings"]["model"]

    pm = ProjectManager(config["storage"]["projects_dir"])
    pm.init_project(project)
    _, session_path = pm.new_session(project)

    emit({"type": "stage", "message": f"Searching for: {query}"})

    clients = [
        ("semantic_scholar", SemanticScholarClient(
            api_key=ss_cfg.get("api_key") or None,
            rate_limit_delay=ss_cfg["rate_limit_delay"],
        )),
        ("openalex", OpenAlexClient(email=oa_cfg.get("email") or None)),
    ]

    source_results: dict[str, dict | None] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            pool.submit(_fetch_source, name, client, query, max_results, flt_cfg, pm, session_path, emit): name
            for name, client in clients
        }
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                source_results[name] = future.result()
            except Exception as exc:
                source_results[name] = None
                emit({"type": "error", "source": name, "message": str(exc)})

    all_passed = [
        p for name, _ in clients
        for p in (source_results.get(name) or {}).get("passed", [])
    ]

    unique, n_doi = deduplicate_by_doi(all_passed)
    unique, n_title = deduplicate_by_title(unique)
    existing = pm.get_all_master_papers(project)
    unique, n_master = filter_known_by_title(unique, [p.get("title") or "" for p in existing])
    emit({"type": "dedup", "doi": n_doi, "title": n_title, "master": n_master, "remaining": len(unique)})

    floor_passed, floor_disc = apply_citation_floor(unique, floor_cfg)
    floor_passed.sort(key=lambda p: p.get("citationCount") or 0, reverse=True)
    emit({"type": "floor", "discarded": len(floor_disc), "remaining": len(floor_passed)})

    if not floor_passed:
        emit({"type": "done", "inserted": 0})
        return

    final_papers = floor_passed
    if context:
        ev_cfg = config["evaluation"]
        thr = ev_cfg["thresholds"]
        w = ev_cfg["weights"]
        emit({"type": "eval_start", "count": len(floor_passed)})
        evaluator = EmbeddingEvaluator(
            model_name=emb_model,
            min_semantic=thr["min_semantic"],
            threshold_relevant=thr["relevant"],
            threshold_potentially=thr["potentially"],
            weight_semantic=w["semantic"],
            weight_impact=w["impact"],
            citation_ref=ev_cfg["citation_ref"],
        )
        evaluated = evaluator.evaluate_batch(floor_passed, context)
        cats: dict[str, int] = {}
        for p in evaluated:
            cats[(p.get("evaluation") or {}).get("category", "error")] = \
                cats.get((p.get("evaluation") or {}).get("category", "error"), 0) + 1
        emit({"type": "eval_done", **cats})
        final_papers = [
            p for p in evaluated
            if (p.get("evaluation") or {}).get("category") in ("relevante", "potencialmente_relevante")
        ]

    chroma_stats = {"added": 0, "skipped": 0}
    master_stats = {"added": 0, "skipped": 0}
    if final_papers:
        chroma = MasterVectorDB(persist_dir=pm.chroma_dir(project), model_name=emb_model)
        chroma_stats = chroma.upsert_papers(final_papers)
        master_stats = pm.upsert_master_papers(project, final_papers)
        export_bibtex(pm.get_all_master_papers(project), pm.bibtex_path(project))

    emit({"type": "insert", "added": chroma_stats["added"], "skipped": chroma_stats["skipped"]})
    emit({"type": "done", "inserted": master_stats.get("added", 0)})


# ── Import pipeline ────────────────────────────────────────────────────────────

def run_import(
    project: str,
    csv_path: str,
    context: str | None,
    config: dict,
    emit: Emit,
) -> dict:
    import csv as csv_mod
    import io as io_mod

    from src.utils.deduplication import deduplicate_by_doi, deduplicate_by_title, filter_known_by_title

    flt_cfg = config["filters"]
    floor_cfg = config["citation_floors"]
    ev_cfg = config["evaluation"]
    emb_model = config["embeddings"]["model"]

    pm = ProjectManager(config["storage"]["projects_dir"])
    pm.init_project(project)
    path = Path(csv_path)

    # Read CSV
    raw_text = None
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            raw_text = path.read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    if raw_text is None:
        return {"error": "Cannot decode CSV file"}

    first_line = next((ln for ln in raw_text.splitlines() if ln.strip()), "")
    sep = "\t" if first_line.count("\t") > first_line.count(",") else ","
    reader = csv_mod.DictReader(io_mod.StringIO(raw_text), delimiter=sep)
    rows = [row for row in reader if any(v and str(v).strip() for v in row.values())]

    if not rows:
        return {"error": "Empty CSV file"}

    # Detect format
    cols = {c.lower().strip() for c in rows[0].keys()}
    scopus_score = ("eid" in cols) * 3 + ("cited by" in cols) * 2 + ("source title" in cols)
    wos_score = ("ut (unique wos id)" in cols) * 3 + ("times cited, all databases" in cols) * 2 + ("article title" in cols) * 2
    fmt = "scopus" if scopus_score >= wos_score else "wos"
    emit({"type": "parse", "rows": len(rows), "format": fmt})

    # Column maps
    SCOPUS = {"title": ["Title"], "abstract": ["Abstract"], "doi": ["DOI"],
               "year": ["Year"], "citations": ["Cited by"], "authors": ["Authors"], "venue": ["Source title"]}
    WOS = {"title": ["Article Title", "TI", "Title"], "abstract": ["Abstract", "AB"],
           "doi": ["DOI", "DI"], "year": ["Publication Year", "Year Published", "PY", "Year"],
           "citations": ["Times Cited, All Databases", "Times Cited, WOS Core", "TC"],
           "authors": ["Authors", "AU"], "venue": ["Source Title", "Full Journal Title", "SO"]}
    col_map = SCOPUS if fmt == "scopus" else WOS

    def _get(row, cands):
        ci = {k.lower().strip(): str(v).strip() for k, v in row.items()}
        for c in cands:
            v = ci.get(c.lower().strip(), "")
            if v and v.lower() != "nan":
                return v
        return ""

    def _clean_doi(raw):
        d = raw.strip()
        for pf in ("https://doi.org/", "http://doi.org/", "doi.org/"):
            if d.lower().startswith(pf):
                d = d[len(pf):]
        return d.strip() or None

    def _parse_int(s):
        try:
            return int(float(s))
        except (ValueError, TypeError):
            return None

    papers_raw = []
    for row in rows:
        doi = _clean_doi(_get(row, col_map["doi"]))
        papers_raw.append({
            "title": _get(row, col_map["title"]),
            "abstract": _get(row, col_map["abstract"]),
            "externalIds": {"DOI": doi},
            "year": _parse_int(_get(row, col_map["year"])),
            "citationCount": _parse_int(_get(row, col_map["citations"])),
            "authors": [{"name": p.strip()} for p in _get(row, col_map["authors"]).split(";") if p.strip()],
            "venue": _get(row, col_map["venue"]),
            "_source": f"{fmt}_csv",
        })

    papers, n_doi = deduplicate_by_doi(papers_raw)
    papers, n_title = deduplicate_by_title(papers)

    master_all = pm.get_all_master_papers(project)
    known_dois = {((p.get("externalIds") or {}).get("DOI") or "").strip().lower()
                  for p in master_all if ((p.get("externalIds") or {}).get("DOI") or "").strip()}
    papers_new = [p for p in papers
                  if not ((p.get("externalIds") or {}).get("DOI") or "").strip().lower() in known_dois
                  or not ((p.get("externalIds") or {}).get("DOI") or "").strip().lower()]
    n_doi_known = len(papers) - len(papers_new)
    papers_new, n_title_known = filter_known_by_title(papers_new, [p.get("title") or "" for p in master_all])

    emit({"type": "dedup", "doi_intra": n_doi, "title_intra": n_title,
          "doi_master": n_doi_known, "title_master": n_title_known, "remaining": len(papers_new)})

    if not papers_new:
        return {"format": fmt, "parsed": len(rows), "inserted": 0,
                "message": "All papers already in master_db"}

    mech_passed, mech_rej = apply_filter(papers_new, **{k: flt_cfg[k] for k in flt_cfg})
    emit({"type": "filter", "passed": len(mech_passed), "rejected": len(mech_rej)})

    floor_passed, floor_disc = apply_citation_floor(mech_passed, floor_cfg)
    floor_passed.sort(key=lambda p: p.get("citationCount") or 0, reverse=True)
    emit({"type": "floor", "discarded": len(floor_disc), "remaining": len(floor_passed)})

    if not floor_passed:
        return {"format": fmt, "parsed": len(rows), "inserted": 0,
                "message": "No papers passed filters"}

    final = floor_passed
    eval_stats = None
    if context and floor_passed:
        thr = ev_cfg["thresholds"]
        w = ev_cfg["weights"]
        emit({"type": "eval_start", "count": len(floor_passed)})
        evaluator = EmbeddingEvaluator(
            model_name=emb_model,
            min_semantic=thr["min_semantic"],
            threshold_relevant=thr["relevant"],
            threshold_potentially=thr["potentially"],
            weight_semantic=w["semantic"],
            weight_impact=w["impact"],
            citation_ref=ev_cfg["citation_ref"],
        )
        evaluated = evaluator.evaluate_batch(floor_passed, context)
        cats: dict[str, int] = {}
        for p in evaluated:
            cats[(p.get("evaluation") or {}).get("category", "error")] = \
                cats.get((p.get("evaluation") or {}).get("category", "error"), 0) + 1
        eval_stats = cats
        emit({"type": "eval_done", **cats})
        final = [p for p in evaluated
                 if (p.get("evaluation") or {}).get("category") in ("relevante", "potencialmente_relevante")]

    chroma_stats = {"added": 0, "skipped": 0}
    master_stats = {"added": 0, "skipped": 0}
    if final:
        chroma = MasterVectorDB(persist_dir=pm.chroma_dir(project), model_name=emb_model)
        chroma_stats = chroma.upsert_papers(final)
        master_stats = pm.upsert_master_papers(project, final)
        export_bibtex(pm.get_all_master_papers(project), pm.bibtex_path(project))

    emit({"type": "insert", "added": chroma_stats["added"], "skipped": chroma_stats["skipped"]})
    emit({"type": "done", "inserted": master_stats.get("added", 0)})

    return {
        "format": fmt,
        "parsed": len(rows),
        "dedup_doi": n_doi,
        "dedup_title": n_title,
        "already_in_db": n_doi_known + n_title_known,
        "mech_passed": len(mech_passed),
        "floor_discarded": len(floor_disc),
        "eval_stats": eval_stats,
        "inserted": master_stats.get("added", 0),
    }
