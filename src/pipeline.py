"""
Search / import / rescore pipelines, shared by the FastAPI backend and the CLI.

Design rules (see AUDITORIA.md):
  * Nothing retrieved is ever deleted. Duplicates are merged, quality problems
    become `flags`, relevance becomes a `score` used for ordering.
  * Every run writes sessions/<id>/session.json with the exact query, date,
    counts per source and config, so the PRISMA flow can be reconstructed.
  * The research context lives at project level; when it changes, the whole
    library is rescored so scores stay comparable.
"""
import concurrent.futures
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Callable

from src.embeddings.model import get_embedder
from src.embeddings.store import EmbeddingStore
from src.evaluation.scoring import score_papers
from src.filters.flags import compute_flags
from src.importers.csv_import import parse_csv
from src.sources.openalex import OpenAlexClient
from src.sources.semantic_scholar import SemanticScholarClient
from src.storage.project_manager import ProjectManager
from src.utils.bibtex_exporter import export_bibtex
from src.utils.deduplication import dedupe_batch, merge_records, match_library
from src.utils.records import finalize_record

Emit = Callable[[dict], None]


def _noop(_event: dict) -> None:
    pass


def _config_snapshot(config: dict) -> dict:
    return {k: config.get(k) for k in ("evaluation", "embeddings", "citation_floors")}


def _store(pm: ProjectManager, project: str, config: dict) -> EmbeddingStore:
    return EmbeddingStore(pm.embeddings_path(project), get_embedder(config))


def _rescore(pm, project, library, context, config) -> None:
    """Recompute evaluation for every paper (cheap: embeddings are cached)."""
    store = _store(pm, project, config)
    if context:
        sims = store.similarities(context, library)
        score_papers(library, sims, config["evaluation"])
    else:
        store.vectors_for(library)  # keep the cache warm for Ask / clusters
        for p in library:
            p.pop("evaluation", None)


def _ingest(pm: ProjectManager, project: str, records_by_source: dict[str, list[dict]],
            session: dict, session_path: Path, context: str | None, config: dict, emit: Emit) -> dict:
    floors = config.get("citation_floors") or {}

    # 1. normalize + provenance
    batch = []
    for source, records in records_by_source.items():
        for r in records:
            rec = finalize_record(r)
            rec["found_in"] = [{
                "session": session["session_id"], "kind": session["kind"],
                "query": session.get("query") or session.get("file"), "source": source,
            }]
            batch.append(rec)
    identified = len(batch)

    # 2. duplicates inside this run
    unique, dup_within = dedupe_batch(batch)

    with pm.lock(project):
        library = pm.get_papers(project)

        # 3. duplicates against the library -> merge provenance into the existing record
        new, matched = match_library(unique, library)
        for paper, idx in matched:
            old = library[idx]
            merged = {**old, **merge_records(old, paper)}
            merged["id"] = old["id"]  # keep ids stable (embeddings, clusters)
            library[idx] = merged
        library.extend(new)
        new_ids = {p["id"] for p in new}
        emit({"type": "dedup", "identified": identified, "within": dup_within,
              "already": len(matched), "new": len(new)})

        # 4. flags (labels only)
        for p in library:
            p["flags"] = compute_flags(p, floors)

        # 5. context (project-level) and scoring
        meta = pm.get_meta(project)
        stored = (meta.get("context") or "").strip()
        effective = (context or "").strip() or stored
        context_changed = effective != stored
        if context_changed:
            pm.set_meta(project, context=effective, context_updated_at=datetime.now().isoformat())
            emit({"type": "context", "updated": True, "rescoring": len(library)})
        if new:
            emit({"type": "embed", "count": len(new)})
        _rescore(pm, project, library, effective, config)

        cats = Counter((p.get("evaluation") or {}).get("category", "unevaluated")
                       for p in library if p["id"] in new_ids)
        if effective:
            emit({"type": "eval_done", **cats})

        pm.save_papers(project, library)
        export_bibtex(library, pm.bibtex_path(project))

    flags_new = Counter(f for p in library if p["id"] in new_ids for f in p["flags"])
    session.update({
        "context": effective,
        "identified": identified,
        "duplicates_within": dup_within,
        "already_in_library": len(matched),
        "added": len(new),
        "library_size": len(library),
        "flags_in_added": dict(flags_new),
        "categories_in_added": dict(cats),
        "config": _config_snapshot(config),
        "finished_at": datetime.now().isoformat(),
    })
    pm.save_session(session_path, session)
    emit({"type": "done", "added": len(new), "already": len(matched), "total": len(library)})
    return session


# ── Search ───────────────────────────────────────────────────────────────────

def run_search(project: str, query: str, context: str | None, max_results: int, config: dict,
               emit: Emit = _noop, year_from: int | None = None, year_to: int | None = None) -> dict:
    pm = ProjectManager(config["storage"]["projects_dir"])
    pm.init_project(project)
    session_id, session_path = pm.new_session(project, "search")
    ss_cfg = config["sources"]["semantic_scholar"]
    oa_cfg = config["sources"]["openalex"]

    clients = {
        "semantic_scholar": SemanticScholarClient(
            api_key=ss_cfg.get("api_key") or None,
            rate_limit_delay=ss_cfg.get("rate_limit_delay", 1.0),
            on_wait=lambda msg: emit({"type": "wait", "source": "semantic_scholar", "message": msg}),
        ),
        "openalex": OpenAlexClient(email=oa_cfg.get("email") or None),
    }
    enabled = [n for n in clients if (config["sources"].get(n) or {}).get("enabled", True)]
    emit({"type": "stage", "message": f"Searching for: {query}"})

    def fetch(name):
        emit({"type": "fetch_start", "source": name})
        records = clients[name].search_all(query, max_results=max_results,
                                           year_from=year_from, year_to=year_to)
        pm.save_raw_results(session_path, name, records)
        emit({"type": "fetch_done", "source": name, "retrieved": len(records)})
        return records

    records_by_source: dict[str, list[dict]] = {}
    sources_info: dict[str, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(enabled) or 1) as pool:
        futures = {pool.submit(fetch, n): n for n in enabled}
        for fut in concurrent.futures.as_completed(futures):
            name = futures[fut]
            try:
                records_by_source[name] = fut.result()
                sources_info[name] = {"retrieved": len(records_by_source[name]), "error": None}
            except Exception as exc:  # one source failing must not kill the run
                sources_info[name] = {"retrieved": 0, "error": str(exc)}
                emit({"type": "error", "source": name, "message": str(exc)})

    session = {
        "session_id": session_id, "kind": "search", "started_at": datetime.now().isoformat(),
        "query": query, "year_from": year_from, "year_to": year_to,
        "max_results_per_source": max_results, "sources": sources_info,
    }
    return _ingest(pm, project, records_by_source, session, session_path, context, config, emit)


# ── CSV import ───────────────────────────────────────────────────────────────

def run_import(project: str, csv_path: str, context: str | None, config: dict,
               emit: Emit = _noop, filename: str | None = None) -> dict:
    pm = ProjectManager(config["storage"]["projects_dir"])
    pm.init_project(project)
    fmt, n_rows, records = parse_csv(csv_path)
    source = f"{fmt}_csv"
    emit({"type": "parse", "rows": n_rows, "format": fmt, "records": len(records)})
    session_id, session_path = pm.new_session(project, "import")
    pm.save_raw_results(session_path, source, records)
    session = {
        "session_id": session_id, "kind": "import", "started_at": datetime.now().isoformat(),
        "file": filename or Path(csv_path).name, "format": fmt, "rows": n_rows,
        "sources": {source: {"retrieved": len(records), "error": None}},
    }
    return _ingest(pm, project, {source: records}, session, session_path, context, config, emit)


# ── Rescore / query / PRISMA ─────────────────────────────────────────────────

def rescore_library(project: str, context: str, config: dict) -> dict:
    pm = ProjectManager(config["storage"]["projects_dir"])
    with pm.lock(project):
        library = pm.get_papers(project)
        context = (context or "").strip()
        pm.set_meta(project, context=context, context_updated_at=datetime.now().isoformat())
        _rescore(pm, project, library, context, config)
        pm.save_papers(project, library)
        export_bibtex(library, pm.bibtex_path(project))
    cats = Counter((p.get("evaluation") or {}).get("category", "unevaluated") for p in library)
    return {"total": len(library), "by_category": dict(cats)}


def semantic_query(project: str, question: str, top: int, config: dict) -> list[dict]:
    pm = ProjectManager(config["storage"]["projects_dir"])
    with pm.lock(project):
        library = pm.get_papers(project)
        if not library:
            return []
        sims = _store(pm, project, config).similarities(question, library)
    order = sims.argsort()[::-1][:top]
    return [{"rank": r + 1, "id": library[i]["id"], "title": library[i].get("title"),
             "year": library[i].get("year"), "venue": library[i].get("venue"),
             "doi": (library[i].get("externalIds") or {}).get("DOI"),
             "similarity": round(float(sims[i]), 4)}
            for r, i in enumerate(order)]


def prisma_summary(project: str, config: dict) -> dict:
    """Numbers for the 'Identification' part of a PRISMA 2020 flow diagram."""
    pm = ProjectManager(config["storage"]["projects_dir"])
    sessions = pm.list_sessions(project)
    library = pm.get_papers(project)
    by_source: Counter = Counter()
    for s in sessions:
        for src, info in (s.get("sources") or {}).items():
            by_source[src] += info.get("retrieved") or 0
    return {
        "identified_by_source": dict(by_source),
        "identified_total": sum(by_source.values()),
        "duplicates_removed": sum((s.get("duplicates_within") or 0) + (s.get("already_in_library") or 0)
                                  for s in sessions),
        "records_in_library": len(library),
        "flagged": dict(Counter(f for p in library for f in p.get("flags") or [])),
        "by_category": dict(Counter((p.get("evaluation") or {}).get("category", "unevaluated")
                                    for p in library)),
        "sessions": [{k: s.get(k) for k in ("session_id", "kind", "started_at", "query", "file",
                                             "year_from", "year_to", "sources", "identified",
                                             "duplicates_within", "already_in_library", "added")}
                     for s in sessions],
    }
