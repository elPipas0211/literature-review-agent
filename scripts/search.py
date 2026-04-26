#!/usr/bin/env python3
"""
Full pipeline: fetch → mechanical filter → deduplicate → citation floor → embedding eval.

Stages:
  1. Semantic Scholar + OpenAlex in parallel → mechanical filter (per source)
  2. Deduplicate by DOI across sources
  3. Apply citation floor (discard old papers with few citations)
  4. Sort by citationCount descending (high citations → most valuable)
  5. [Optional] Evaluate by cosine similarity when --context is provided
  6. Save consolidated results

Usage:
    python scripts/search.py --project <name> --query "<query>" \\
        [--max-results N] \\
        [--context "research context description"] \\
        [--min-cit-pre2015 N] [--min-cit-mid N]
"""
import argparse
import concurrent.futures
import logging
import sys
from pathlib import Path

import yaml

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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_config(path: str = "config.yaml") -> dict:
    """Load YAML configuration. All pipeline parameters live here so no values are hard-coded."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Per-source helpers
# ---------------------------------------------------------------------------

def run_source(
    source: str,
    client,
    query: str,
    max_results: int,
    flt_cfg: dict,
    pm: ProjectManager,
    session_path: Path,
) -> dict:
    """
    Fetch papers from one API and apply the mechanical pre-filter.

    Runs synchronously but is called in a thread pool so both sources execute
    in parallel. Returns a dict with raw/passed/rejected counts and the save path.
    """
    logger.info(f"[{source}] Querying: '{query}'  (max {max_results})")
    raw = client.search_all(query, max_results=max_results)
    logger.info(f"[{source}] Retrieved {len(raw)} papers")

    passed, rejected = apply_filter(
        raw,
        require_abstract=flt_cfg["require_abstract"],
        require_doi=flt_cfg["require_doi"],
        require_citation_count=flt_cfg["require_citation_count"],
    )
    logger.info(f"[{source}] Passed mechanical filter: {len(passed)} / {len(raw)}")

    out = pm.save_query_results(session_path, query, source, passed, rejected)
    return {"source": source, "query": query, "raw": raw, "passed": passed, "rejected": rejected, "out": out}


def _print_source_summary(r: dict, flt_cfg: dict) -> None:
    """Print a per-source rejection breakdown to help diagnose over-aggressive filters."""
    breakdown: dict[str, int] = {}
    for p in r["rejected"]:
        for reason in p.get("filter_reasons", []):
            breakdown[reason] = breakdown.get(reason, 0) + 1

    raw, passed, rejected = r["raw"], r["passed"], r["rejected"]
    label = r["source"].replace("_", " ").title()
    print(f"\n{'─'*60}")
    print(f"  Fuente       : {label}")
    print(f"  Query        : {r['query']}")
    print(f"  Retrieved    : {len(raw)}")
    print(f"  Passed       : {len(passed)}")
    print(f"  Rejected     : {len(rejected)}")
    if len(raw) == 0:
        print("  [!] La API no devolvió resultados")
    elif len(passed) == 0:
        print("  [!] Todos rechazados por el filtro mecánico")
    if breakdown:
        print("\n  Motivos de rechazo:")
        for reason, count in sorted(breakdown.items(), key=lambda x: -x[1]):
            pct = count / len(raw) * 100 if raw else 0
            print(f"    {reason:<30} {count:>3}  ({pct:.0f}%)")
    active = [k.replace("require_", "") for k, v in flt_cfg.items() if k.startswith("require_") and v]
    print(f"\n  Filtros activos : {', '.join(active) or 'ninguno'}")
    print(f"{'─'*60}")
    if passed:
        print("\n  Sample (primeros 3):")
        for p in passed[:3]:
            doi = (p.get("externalIds") or {}).get("DOI", "—")
            print(f"    [{p.get('year')}] {(p.get('title') or '—')[:70]}  DOI:{doi}")
    elif rejected:
        print("\n  Muestra rechazados (primeros 3):")
        for p in rejected[:3]:
            reasons = ", ".join(p.get("filter_reasons", []))
            print(f"    [{p.get('year')}] {(p.get('title') or '—')[:60]}")
            print(f"           → {reasons}")


# ---------------------------------------------------------------------------
# Pipeline summary
# ---------------------------------------------------------------------------

def _print_pipeline_summary(
    source_counts: dict,
    n_dupes: int,
    n_title_batch: int,
    n_title_master: int,
    floor_discarded: list,
    eval_stats: dict | None,
    final_papers: list,
    out: Path,
) -> None:
    """Print an end-of-pipeline summary: attrition at each stage plus top/bottom scored papers."""
    print(f"\n{'═'*60}")
    print("  RESUMEN DEL PIPELINE")
    print(f"{'═'*60}")
    total = sum(source_counts.values())
    for src, count in source_counts.items():
        label = src.replace("_", " ").title()
        print(f"  {label:<32} {count:>4} passed mechanical filter")
    print(f"  {'─'*44}")
    print(f"  {'Total antes de dedup':<32} {total:>4}")
    print(f"  {'Duplicados eliminados (DOI)':<32} {n_dupes:>4}")
    if n_title_batch:
        print(f"  {'Duplicados eliminados (título)':<32} {n_title_batch:>4}")
    if n_title_master:
        print(f"  {'Ya en master_db (título similar)':<32} {n_title_master:>4}")
    print(f"  {'Eliminados por citation floor':<32} {len(floor_discarded):>4}")
    if floor_discarded:
        pre = sum(1 for p in floor_discarded if (p.get("year") or 9999) < 2015)
        mid = sum(1 for p in floor_discarded if 2015 <= (p.get("year") or 0) <= 2020)
        if pre: print(f"    {'pre-2015':<30} {pre:>4}")
        if mid: print(f"    {'2015-2020':<30} {mid:>4}")
    if eval_stats:
        print(f"\n  {'Evaluados':<32} {eval_stats['total']:>4}")
        for cat in ("descartado_semantica", "relevante", "potencialmente_relevante", "no_relevante", "error"):
            n = eval_stats.get(cat, 0)
            if n: print(f"    {cat:<30} {n:>4}")
    print(f"\n  {'Papers en resultado final':<32} {len(final_papers):>4}")
    print(f"  Output: {out}")

    # Top / bottom 3 by combined score
    scored = [p for p in final_papers if isinstance(p.get("evaluation"), dict)
              and p["evaluation"].get("score") is not None]
    if scored:
        ranked = sorted(scored, key=lambda p: p["evaluation"]["score"], reverse=True)

        def _paper_line(rank: int, p: dict) -> None:
            ev = p["evaluation"]
            title = (p.get("title") or "")[:55]
            cites = p.get("citationCount", "?")
            print(f"    {rank}. [{ev['score']:.4f}] {title}")
            print(f"         sem={ev['semantic_score']:.4f}  "
                  f"imp={ev['impact_score']:.4f}  "
                  f"cites={cites}")

        print(f"\n  Top 3 (score mas alto):")
        for i, p in enumerate(ranked[:3], 1):
            _paper_line(i, p)

        if len(ranked) > 3:
            print(f"\n  Bottom 3 (score mas bajo):")
            for i, p in enumerate(ranked[-3:][::-1], 1):
                _paper_line(i, p)

    print(f"{'═'*60}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Orchestrate the 10-stage pipeline:

    1–2. Fetch from Semantic Scholar + OpenAlex in parallel, then mechanical filter.
    3.   Deduplicate by DOI across sources; 3b by title similarity; 3c against master_db.
    4.   Citation floor: discard old papers with too few citations.
    5.   Sort by citation count (proxy for quality when no context is given).
    6.   Embedding evaluation (cosine sim + log-impact) — only when --context is supplied.
    7.   Save consolidated session results to disk.
    8.   Upsert accepted papers into the persistent ChromaDB vector store.
    9.   Merge into master papers.json.
    10.  Regenerate master.bib.
    """
    parser = argparse.ArgumentParser(description="Full literature review pipeline")
    parser.add_argument("--project", required=True, help="Project name (folder under projects/)")
    parser.add_argument("--query", required=True, help="Search query string")
    parser.add_argument("--max-results", type=int, default=50, help="Max papers per source (default 50)")
    parser.add_argument("--context", default=None,
                        help="Research context for embedding evaluation. Enables cosine similarity eval when provided.")
    parser.add_argument("--min-semantic", type=float, default=None,
                        help="Override: minimum semantic score (default from config)")
    parser.add_argument("--min-cit-pre2015", type=int, default=None,
                        help="Override: min citations for papers with year < 2015")
    parser.add_argument("--min-cit-mid", type=int, default=None,
                        help="Override: min citations for papers 2015-2020")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    ss_cfg = config["sources"]["semantic_scholar"]
    oa_cfg = config["sources"]["openalex"]
    flt_cfg = config["filters"]
    floor_cfg = config["citation_floors"]

    # CLI overrides for citation floors
    if args.min_cit_pre2015 is not None:
        floor_cfg["pre_2015"]["min_citations"] = args.min_cit_pre2015
    if args.min_cit_mid is not None:
        floor_cfg["mid_range"]["min_citations"] = args.min_cit_mid

    pm = ProjectManager(config["storage"]["projects_dir"])
    pm.init_project(args.project)
    session_id, session_path = pm.new_session(args.project)
    logger.info(f"Project: {args.project}  |  Session: {session_id}")

    # ── Stage 1: Parallel fetch + mechanical filter ────────────────────────
    clients = [
        ("semantic_scholar", SemanticScholarClient(
            api_key=ss_cfg.get("api_key") or None,
            rate_limit_delay=ss_cfg["rate_limit_delay"],
        )),
        ("openalex", OpenAlexClient(
            email=oa_cfg.get("email") or None,
        )),
    ]

    source_results: dict[str, dict | None] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            pool.submit(run_source, name, client, args.query, args.max_results, flt_cfg, pm, session_path): name
            for name, client in clients
        }
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                source_results[name] = future.result()
            except Exception as exc:
                logger.error(f"[{name}] Error: {exc}", exc_info=True)
                source_results[name] = None

    # Print per-source summaries in deterministic order
    for source_name, _ in clients:
        r = source_results.get(source_name)
        if r is None:
            print(f"\n{'─'*60}\n  Fuente: {source_name}  —  ERROR (ver logs)\n{'─'*60}")
            continue
        _print_source_summary(r, flt_cfg)

    # ── Stage 2: Deduplicate by DOI ────────────────────────────────────────
    all_passed = [
        p for name, _ in clients
        for p in (source_results.get(name) or {}).get("passed", [])
    ]
    source_counts = {
        name: len((source_results.get(name) or {}).get("passed", []))
        for name, _ in clients
    }
    unique_papers, n_dupes = deduplicate_by_doi(all_passed)
    logger.info(f"Dedup DOI: {len(unique_papers)} unique ({n_dupes} removed)")

    # ── Stage 2b: Deduplicate by title similarity (intra-batch) ───────────
    unique_papers, n_title_batch = deduplicate_by_title(unique_papers)
    logger.info(f"Dedup title (batch): {n_title_batch} near-duplicate titles removed")

    # ── Stage 2c: Filter titles already present in master_db ──────────────
    existing_master = pm.get_all_master_papers(args.project)
    master_titles = [p.get("title") or "" for p in existing_master]
    unique_papers, n_title_master = filter_known_by_title(unique_papers, master_titles)
    logger.info(f"Dedup title (master): {n_title_master} titles matching master_db removed")

    # ── Stage 3: Citation floor ────────────────────────────────────────────
    floor_passed, floor_discarded = apply_citation_floor(unique_papers, floor_cfg)
    logger.info(f"Citation floor: {len(floor_passed)} passed, {len(floor_discarded)} discarded")

    # ── Stage 4: Sort by citations descending ─────────────────────────────
    floor_passed.sort(key=lambda p: p.get("citationCount") or 0, reverse=True)

    # ── Stage 5: Embedding evaluation (optional) ──────────────────────────
    final_papers = floor_passed
    eval_stats: dict | None = None

    if args.context:
        ev_cfg = config["evaluation"]
        thr = ev_cfg["thresholds"]
        w = ev_cfg["weights"]
        emb_model = config["embeddings"]["model"]
        min_sem = args.min_semantic if args.min_semantic is not None else thr["min_semantic"]
        evaluator = EmbeddingEvaluator(
            model_name=emb_model,
            min_semantic=min_sem,
            threshold_relevant=thr["relevant"],
            threshold_potentially=thr["potentially"],
            weight_semantic=w["semantic"],
            weight_impact=w["impact"],
            citation_ref=ev_cfg["citation_ref"],
        )
        logger.info(f"Evaluating {len(floor_passed)} papers with {emb_model}...")
        evaluated = evaluator.evaluate_batch(floor_passed, args.context)

        cats: dict[str, int] = {}
        for p in evaluated:
            cat = (p.get("evaluation") or {}).get("category", "error")
            cats[cat] = cats.get(cat, 0) + 1
        eval_stats = {"total": len(evaluated), **cats}

        final_papers = [
            p for p in evaluated
            if (p.get("evaluation") or {}).get("category") in ("relevante", "potencialmente_relevante")
        ]
        logger.info(f"After evaluation: {len(final_papers)} relevant papers saved")

    # ── Stage 6: Save consolidated ─────────────────────────────────────────
    stats = {
        "query": args.query,
        "context": args.context,
        "source_counts": source_counts,
        "n_duplicates_removed": n_dupes,
        "n_title_dupes_batch": n_title_batch,
        "n_title_dupes_master": n_title_master,
        "n_citation_floor_discarded": len(floor_discarded),
        "citation_floors_applied": floor_cfg,
        "eval_stats": eval_stats,
    }
    out = pm.save_consolidated(session_path, final_papers, stats)

    # ── Stage 7: Upsert to ChromaDB ────────────────────────────────────────
    if final_papers:
        emb_model = config["embeddings"]["model"]
        chroma = MasterVectorDB(
            persist_dir=pm.chroma_dir(args.project),
            model_name=emb_model,
        )
        chroma_stats = chroma.upsert_papers(final_papers)
        logger.info(
            f"ChromaDB: {chroma_stats['added']} added, "
            f"{chroma_stats['skipped']} skipped (already present). "
            f"Total in DB: {chroma.count()}"
        )
    else:
        chroma_stats = {"added": 0, "skipped": 0}

    # ── Stage 8: Update master papers.json ────────────────────────────────
    master_stats = pm.upsert_master_papers(args.project, final_papers)
    logger.info(
        f"Master DB: {master_stats['added']} new papers added, "
        f"{master_stats['skipped']} already existed"
    )

    # ── Stage 9: Export BibTeX ────────────────────────────────────────────
    all_papers = pm.get_all_master_papers(args.project)
    bib_path = pm.bibtex_path(args.project)
    n_bib = export_bibtex(all_papers, bib_path)
    logger.info(f"BibTeX exported: {n_bib} entries → {bib_path}")

    # ── Stage 10: Print summary ────────────────────────────────────────────
    _print_pipeline_summary(
        source_counts, n_dupes, n_title_batch, n_title_master,
        floor_discarded, eval_stats, final_papers, out,
    )
    print(f"  ChromaDB  : +{chroma_stats['added']} new  ({chroma_stats['skipped']} ya existían)  total={chroma.count() if final_papers else '—'}")
    print(f"  Master DB : +{master_stats['added']} new  ({master_stats['skipped']} ya existían)")
    print(f"  BibTeX    : {n_bib} entradas → {bib_path}")
    print()


if __name__ == "__main__":
    main()
