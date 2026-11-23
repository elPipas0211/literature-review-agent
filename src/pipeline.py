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
import functools
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Callable

from src.embeddings.model import get_embedder
from src.embeddings.store import EmbeddingStore
from src.evaluation.scoring import score_papers
from src.filters.flags import compute_flags
from src.importers.bibtex_import import looks_like_bibtex, parse_bibtex
from src.importers.csv_import import parse_csv
from src.keywords import extract_keywords
from src.sources.openalex import OpenAlexClient
from src.storage.project_manager import ProjectManager, discard_unfinished, track_sessions
from src.utils.bibtex_exporter import export_bibtex
from src.utils.deduplication import dedupe_batch, merge_records, match_library
from src.utils.records import finalize_record, get_doi

Emit = Callable[[dict], None]


def _noop(_event: dict) -> None:
    pass


class JobCancelled(Exception):
    """Raised by an emit callback when the user cancelled the run."""


def _runs_atomically(fn):
    """
    A run either finishes (papers + session.json saved) or leaves no trace:
    if it raises - an error or JobCancelled from emit - its unfinished session
    folder is deleted. papers.json is only written right before session.json,
    and nothing after that point can be cancelled.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        track_sessions()
        try:
            return fn(*args, **kwargs)
        except BaseException:
            discard_unfinished()
            raise
    return wrapper


def _openalex(config: dict, emit: Emit) -> OpenAlexClient:
    oa = (config.get("sources") or {}).get("openalex") or {}
    return OpenAlexClient(
        email=oa.get("email") or None,
        api_key=oa.get("api_key") or None,
        on_wait=lambda msg: emit({"type": "wait", "source": "openalex", "message": msg}),
        on_progress=lambda n: emit({"type": "fetch_progress", "source": "openalex", "retrieved": n}),
    )


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
        missing_kw = [p for p in library if p.get("keywords") is None]
        if missing_kw:
            emit({"type": "keywords", "count": len(missing_kw)})
            extract_keywords(missing_kw, get_embedder(config),
                             (config.get("keywords") or {}).get("per_paper", 5))

        cats = Counter((p.get("evaluation") or {}).get("category", "unevaluated")
                       for p in library if p["id"] in new_ids)
        if effective:
            emit({"type": "eval_done", **cats})
        emit({"type": "stage", "message": "Saving…"})  # last point where a cancel is honored

        # ── commit point: no emit (so no cancellation) until session.json is written ──
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

@_runs_atomically
def run_search(project: str, query: str, context: str | None, max_results: int, config: dict,
               emit: Emit = _noop, year_from: int | None = None, year_to: int | None = None) -> dict:
    pm = ProjectManager(config["storage"]["projects_dir"])
    pm.init_project(project)
    session_id, session_path = pm.new_session(project, "search")
    client = _openalex(config, emit)
    emit({"type": "stage", "message": f"Searching OpenAlex for: {query}"})
    emit({"type": "fetch_start", "source": "openalex"})
    records = client.search_all(query, max_results=max_results, year_from=year_from, year_to=year_to)
    pm.save_raw_results(session_path, "openalex", records)
    emit({"type": "fetch_done", "source": "openalex", "retrieved": len(records)})
    records_by_source = {"openalex": records}
    sources_info = {"openalex": {"retrieved": len(records), "error": None}}

    session = {
        "session_id": session_id, "kind": "search", "started_at": datetime.now().isoformat(),
        "query": query, "year_from": year_from, "year_to": year_to,
        "max_results": max_results, "sources": sources_info,
    }
    return _ingest(pm, project, records_by_source, session, session_path, context, config, emit)


# ── CSV import ───────────────────────────────────────────────────────────────

@_runs_atomically
def run_import(project: str, csv_path: str, context: str | None, config: dict,
               emit: Emit = _noop, filename: str | None = None) -> dict:
    pm = ProjectManager(config["storage"]["projects_dir"])
    pm.init_project(project)
    if looks_like_bibtex(csv_path):
        fmt, n_rows, records = parse_bibtex(csv_path)
        file_type = "bibtex"
        source = "bibtex" if fmt == "bibtex" else f"{fmt}_bib"
    else:
        fmt, n_rows, records = parse_csv(csv_path)
        file_type = "csv"
        source = f"{fmt}_csv"
    emit({"type": "parse", "rows": n_rows, "format": fmt, "file_type": file_type, "records": len(records)})
    session_id, session_path = pm.new_session(project, "import")
    pm.save_raw_results(session_path, source, records)
    session = {
        "session_id": session_id, "kind": "import", "started_at": datetime.now().isoformat(),
        "file": filename or Path(csv_path).name, "format": fmt, "file_type": file_type, "rows": n_rows,
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


def refresh_keywords(project: str, config: dict, emit: Emit = _noop) -> dict:
    """
    Re-extract the keyphrases of every paper (e.g. after the keyword filter improved).
    The slow part runs on a copy, outside the project lock, so starring papers
    meanwhile still works; only the keywords are written back.
    """
    pm = ProjectManager(config["storage"]["projects_dir"])
    work = [{"id": p["id"], "title": p.get("title"), "abstract": p.get("abstract"), "keywords": None}
            for p in pm.get_papers(project)]
    emit({"type": "keywords", "count": len(work)})
    extract_keywords(work, get_embedder(config), (config.get("keywords") or {}).get("per_paper", 5),
                     on_progress=lambda done, total: emit({"type": "keywords_progress", "done": done, "total": total}))
    fresh = {w["id"]: w["keywords"] for w in work if w["keywords"] is not None}
    emit({"type": "stage", "message": "Saving…"})
    with pm.lock(project):
        library = pm.get_papers(project)
        for p in library:
            if p["id"] in fresh:
                p["keywords"] = fresh[p["id"]]
        pm.save_papers(project, library)
    return {"updated": len(fresh)}


def _lacks_citation_details(p: dict) -> bool:
    return bool(get_doi(p)) and not (p.get("volume") or p.get("pages"))


def complete_citation_details(project: str, config: dict, emit: Emit = _noop) -> dict:
    """
    Fill volume / issue / pages (needed for APA references) from OpenAlex, by DOI,
    for papers that lack them. Only empty fields are written; scores, flags and
    PRISMA counts are untouched because no record is added.
    """
    pm = ProjectManager(config["storage"]["projects_dir"])
    todo = [get_doi(p) for p in pm.get_papers(project) if _lacks_citation_details(p)]
    emit({"type": "details", "count": len(todo)})
    client = _openalex(config, emit)
    found: dict[str, dict] = {}
    for i in range(0, len(todo), 50):
        found.update(client.biblio_by_doi(todo[i:i + 50]))
        emit({"type": "details_progress", "done": min(i + 50, len(todo)), "total": len(todo)})
    emit({"type": "stage", "message": "Saving…"})
    updated = 0
    with pm.lock(project):
        library = pm.get_papers(project)
        for p in library:
            info = found.get(get_doi(p) or "")
            if not info:
                continue
            changed = False
            for field in ("volume", "issue", "pages", "openalexId"):
                if info.get(field) and not p.get(field):
                    p[field] = info[field]
                    changed = changed or field != "openalexId"
            updated += changed
        pm.save_papers(project, library)
    return {"checked": len(todo), "found": len(found), "updated": updated}


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
    """
    Numbers for the 'Identification' part of a PRISMA 2020 flow diagram.
    Database searches / CSV imports and citation searching (snowballing) are
    reported separately, as PRISMA 2020 asks.
    """
    pm = ProjectManager(config["storage"]["projects_dir"])
    sessions = pm.list_sessions(project)
    library = pm.get_papers(project)

    def block(kinds):
        chosen = [s for s in sessions if s.get("kind") in kinds]
        by_source: Counter = Counter()
        for s in chosen:
            for src, info in (s.get("sources") or {}).items():
                by_source[src] += info.get("retrieved") or 0
        return {
            "identified_by_source": dict(by_source),
            "identified_total": sum(by_source.values()),
            "duplicates_removed": sum((s.get("duplicates_within") or 0) + (s.get("already_in_library") or 0)
                                      for s in chosen),
            "added": sum(s.get("added") or 0 for s in chosen),
        }

    databases = block({"search", "import"})
    citations = block({"snowball"})
    return {
        **databases,  # kept at top level for backwards compatibility
        "databases": databases,
        "citation_searching": citations,
        "records_in_library": len(library),
        "reviews_in_library": sum(1 for p in library if p.get("is_review")),
        "starred": sum(1 for p in library if p.get("starred")),
        "flagged": dict(Counter(f for p in library for f in p.get("flags") or [])),
        "by_category": dict(Counter((p.get("evaluation") or {}).get("category", "unevaluated")
                                    for p in library)),
        "sessions": [{k: s.get(k) for k in ("session_id", "kind", "started_at", "query", "file",
                                             "year_from", "year_to", "max_results", "seed", "direction",
                                             "sources", "identified", "duplicates_within",
                                             "already_in_library", "added")}
                     for s in sessions],
    }


# ── Snowballing (citation searching) ─────────────────────────────────────────

@_runs_atomically
def run_snowball(project: str, paper_id: str, direction: str, max_results: int, config: dict,
                 emit: Emit = _noop) -> dict:
    """Add the references of a paper (backward), the papers citing it (forward), or both."""
    if direction not in ("references", "citations", "both"):
        raise ValueError("direction must be references, citations or both")
    pm = ProjectManager(config["storage"]["projects_dir"])
    library = pm.get_papers(project)
    seed = next((p for p in library if p["id"] == paper_id), None)
    if seed is None:
        raise ValueError(f"Paper {paper_id} is not in the project")
    client = _openalex(config, emit)

    work_id = seed.get("openalexId")
    if not work_id:
        emit({"type": "stage", "message": "Looking up the paper in OpenAlex…"})
        work_id = client.find_work_id((seed.get("externalIds") or {}).get("DOI"), seed.get("title"))
        if not work_id:
            raise ValueError("This paper could not be found in OpenAlex, so its citations are unavailable.")
        with pm.lock(project):  # remember it for next time
            lib = pm.get_papers(project)
            for p in lib:
                if p["id"] == paper_id:
                    p["openalexId"] = work_id
            pm.save_papers(project, lib)

    title = (seed.get("title") or "")[:80]
    session_id, session_path = pm.new_session(project, "snowball")
    records: list[dict] = []
    if direction in ("references", "both"):
        emit({"type": "fetch_start", "source": "references"})
        refs = client.references(work_id, max_results)
        emit({"type": "fetch_done", "source": "references", "retrieved": len(refs)})
        records += refs
    if direction in ("citations", "both"):
        emit({"type": "fetch_start", "source": "citations"})
        cites = client.citing(work_id, max_results)
        emit({"type": "fetch_done", "source": "citations", "retrieved": len(cites)})
        records += cites
    for r in records:
        r["_source"] = "citation_search"
    pm.save_raw_results(session_path, "citation_search", records)
    label = {"references": "references of", "citations": "papers citing", "both": "citations of"}[direction]
    session = {
        "session_id": session_id, "kind": "snowball", "started_at": datetime.now().isoformat(),
        "query": f"{label}: {title}", "seed": paper_id, "direction": direction, "max_results": max_results,
        "sources": {"citation_search": {"retrieved": len(records), "error": None}},
    }
    return _ingest(pm, project, {"citation_search": records}, session, session_path, None, config, emit)


# ── Reading list ─────────────────────────────────────────────────────────────

VALIDATION_LABELS = {"relevant", "irrelevant", "unsure"}


def annotate(project: str, paper_id: str, config: dict, starred: bool | None = None,
             note: str | None = None, validation: str | None = None) -> dict:
    pm = ProjectManager(config["storage"]["projects_dir"])
    with pm.lock(project):
        library = pm.get_papers(project)
        for p in library:
            if p["id"] == paper_id:
                if starred is not None:
                    p["starred"] = bool(starred)
                if note is not None:
                    p["note"] = note.strip()
                if validation is not None:  # "" clears the label
                    if validation and validation not in VALIDATION_LABELS:
                        raise ValueError(f"Unknown label '{validation}'")
                    if validation:
                        p["validation"] = validation
                    else:
                        p.pop("validation", None)
                pm.save_papers(project, library)
                return {"id": paper_id, "starred": p.get("starred", False), "note": p.get("note", ""),
                        "validation": p.get("validation")}
    raise ValueError(f"Paper {paper_id} is not in the project")


# ── Ranking validation ───────────────────────────────────────────────────────

def draw_validation_sample(project: str, size: int, config: dict, seed: int | None = None) -> dict:
    """
    Add `size` papers, drawn by simple random sampling from those not yet in the
    sample, to the project's validation sample. Simple random sampling keeps the
    precision / recall estimates unbiased for the whole library.
    """
    import random

    pm = ProjectManager(config["storage"]["projects_dir"])
    with pm.lock(project):
        meta = pm.get_meta(project)
        sample = list(meta.get("validation_sample") or [])
        ids = [p["id"] for p in pm.get_papers(project)]
        pool = sorted(set(ids) - set(sample))
        rng = random.Random(seed)
        added = rng.sample(pool, min(size, len(pool)))
        sample += added
        draws = list(meta.get("validation_draws") or [])
        draws.append({"at": datetime.now().isoformat(timespec="seconds"), "added": len(added),
                      "library_size": len(ids)})
        pm.set_meta(project, validation_sample=sample, validation_draws=draws)
    return {"sample": sample, "added": len(added), "draws": draws}


# ── Global trends ────────────────────────────────────────────────────────────

def global_trend(query: str, config: dict, year_from: int | None = None, year_to: int | None = None) -> dict:
    """Works per year in all of OpenAlex for a topic, plus a simple growth figure."""
    counts = _openalex(config, _noop).yearly_counts(query, year_from, year_to)
    this_year = datetime.now().year
    full = {r["year"]: r["count"] for r in counts if r["year"] < this_year}
    recent = sum(full.get(y, 0) for y in range(this_year - 3, this_year))
    before = sum(full.get(y, 0) for y in range(this_year - 6, this_year - 3))
    return {
        "query": query,
        "counts": counts,
        "partial_year": this_year,
        "recent_3y": recent,
        "previous_3y": before,
        "growth": round(recent / before - 1, 3) if before else None,
        "total": sum(r["count"] for r in counts),
    }
