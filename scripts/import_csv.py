#!/usr/bin/env python3
"""
Import papers from a manually-exported Scopus or WoS CSV file into a project.

Auto-detects format, maps columns to the internal schema, applies the same
mechanical filter + citation floor + (optional) embedding evaluation as the
main pipeline, deduplicates against master_db, then inserts new papers into
ChromaDB and regenerates master.bib.

Usage:
    python scripts/import_csv.py  --project <name>  --file <path>
                                   [--context "research context"]
                                   [--min-cit-pre2015 N]
                                   [--min-cit-mid N]
                                   [--min-semantic F]
                                   [--config config.yaml]
"""
import argparse
import csv
import io
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.embeddings.chroma_store import MasterVectorDB
from src.evaluation.embedding_evaluator import EmbeddingEvaluator
from src.filters.citation_floor import apply_citation_floor
from src.filters.mechanical import apply_filter
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


# ─────────────────────────────────────────────────────────────────────────────
# Column maps
# Each value is a list of candidate column names, first non-empty match wins.
# Matching is case-insensitive (see _get()).
# ─────────────────────────────────────────────────────────────────────────────

_SCOPUS_COLS: dict[str, list[str]] = {
    "title":     ["Title"],
    "abstract":  ["Abstract"],
    "doi":       ["DOI"],
    "year":      ["Year"],
    "citations": ["Cited by"],
    "authors":   ["Authors"],
    "venue":     ["Source title"],
}

# WoS exports may use different column names depending on the export version
_WOS_COLS: dict[str, list[str]] = {
    "title":     ["Article Title", "TI", "Title"],
    "abstract":  ["Abstract", "AB"],
    "doi":       ["DOI", "DI"],
    "year":      ["Publication Year", "Year Published", "PY", "Year"],
    "citations": [
        "Times Cited, All Databases",
        "Times Cited, WOS Core",
        "Times Cited, All Databases (Web of Science)",
        "TC",
    ],
    "authors":   ["Authors", "AU"],
    "venue":     ["Source Title", "Full Journal Title", "SO", "Journal Title"],
}


# ─────────────────────────────────────────────────────────────────────────────
# CSV reading
# ─────────────────────────────────────────────────────────────────────────────

def _read_csv(path: Path) -> list[dict]:
    """
    Read a CSV or tab-delimited file.
    Tries UTF-8 BOM, UTF-8, then Latin-1 encoding.
    Auto-detects comma vs tab separator from the first non-empty line.
    Strips completely blank rows.
    """
    raw: str | None = None
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            raw = path.read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue

    if raw is None:
        raise ValueError(f"Cannot decode '{path}' with UTF-8 or Latin-1.")

    first_line = next((ln for ln in raw.splitlines() if ln.strip()), "")
    sep = "\t" if first_line.count("\t") > first_line.count(",") else ","

    reader = csv.DictReader(io.StringIO(raw), delimiter=sep)
    return [row for row in reader if any(v and str(v).strip() for v in row.values())]


# ─────────────────────────────────────────────────────────────────────────────
# Format detection
# ─────────────────────────────────────────────────────────────────────────────

def _detect_format(columns: set[str]) -> str:
    """
    Return 'scopus' or 'wos' based on the signature columns present.
    Raises ValueError if the format cannot be determined.
    """
    cols = {c.lower().strip() for c in columns}

    scopus_score = (
        ("eid" in cols) * 3 +
        ("cited by" in cols) * 2 +
        ("source title" in cols) +
        ("document type" in cols)
    )
    wos_score = (
        ("ut (unique wos id)" in cols) * 3 +
        ("times cited, all databases" in cols) * 2 +
        ("article title" in cols) * 2 +
        ("publication year" in cols) +
        ("full journal title" in cols)
    )

    if scopus_score > wos_score:
        return "scopus"
    if wos_score > scopus_score:
        return "wos"

    # Tie-break with single strong indicators
    if "eid" in cols or "cited by" in cols:
        return "scopus"
    if "ut (unique wos id)" in cols or "article title" in cols:
        return "wos"

    raise ValueError(
        "Cannot determine CSV format (Scopus or WoS).\n"
        f"  Detected columns (first 15): {sorted(columns)[:15]}\n"
        "  Scopus exports include: EID, 'Cited by'\n"
        "  WoS exports include: 'UT (Unique WOS ID)', 'Article Title', "
        "'Times Cited, All Databases'"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Paper normalization
# ─────────────────────────────────────────────────────────────────────────────

def _get(row: dict, candidates: list[str]) -> str:
    """Case-insensitive column lookup; returns first non-empty value."""
    row_ci = {k.lower().strip(): str(v).strip() for k, v in row.items()}
    for col in candidates:
        val = row_ci.get(col.lower().strip(), "")
        if val and val.lower() != "nan":
            return val
    return ""


def _clean_doi(raw: str) -> str | None:
    """Strip URL prefixes and whitespace; return None for empty DOIs."""
    doi = raw.strip()
    if not doi:
        return None
    for prefix in ("https://doi.org/", "http://doi.org/", "doi.org/"):
        if doi.lower().startswith(prefix):
            doi = doi[len(prefix):]
    return doi.strip() or None


def _parse_int(s: str) -> int | None:
    """Parse int from string; handles '2020.0' from Excel exports."""
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def _parse_authors(raw: str, fmt: str) -> list[dict]:
    """
    Split author string on ';' into name dicts.
    WoS old-format names are ALL CAPS → title-cased.
    """
    if not raw or not raw.strip():
        return []
    parts = [p.strip() for p in raw.split(";") if p.strip()]
    if fmt == "wos":
        # Title-case only entirely uppercase names (old WoS format)
        parts = [
            p.title() if p == p.upper() and len(p) > 2 else p
            for p in parts
        ]
    return [{"name": p} for p in parts]


def _normalize_paper(
    row: dict,
    col_map: dict[str, list[str]],
    fmt: str,
    csv_path: str,
) -> dict:
    doi = _clean_doi(_get(row, col_map["doi"]))
    return {
        "title":         _get(row, col_map["title"]),
        "abstract":      _get(row, col_map["abstract"]),
        "externalIds":   {"DOI": doi},
        "year":          _parse_int(_get(row, col_map["year"])),
        "citationCount": _parse_int(_get(row, col_map["citations"])),
        "authors":       _parse_authors(_get(row, col_map["authors"]), fmt),
        "venue":         _get(row, col_map["venue"]),
        "_source":       f"{fmt}_csv",
        "_csv_file":     csv_path,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Master-DB deduplication helpers
# ─────────────────────────────────────────────────────────────────────────────

def _filter_known(
    papers: list[dict],
    known_dois: set[str],
) -> tuple[list[dict], int]:
    """Remove papers whose DOI is already in master_db. Returns (new, n_skipped)."""
    new, skipped = [], 0
    for p in papers:
        doi = ((p.get("externalIds") or {}).get("DOI") or "").strip().lower()
        if doi and doi in known_dois:
            skipped += 1
        else:
            new.append(p)
    return new, skipped


# ─────────────────────────────────────────────────────────────────────────────
# Session log
# ─────────────────────────────────────────────────────────────────────────────

def _save_import_log(session_path: Path, metadata: dict) -> None:
    """Persist a JSON audit record for the import so the session history is traceable."""
    payload = {"created_at": datetime.now().isoformat(), **metadata}
    (session_path / "import_log.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Output helpers
# ─────────────────────────────────────────────────────────────────────────────

W = 62


def _hline(char: str = "─") -> None:
    print(f"  {char * W}")


def _row(label: str, value) -> None:
    print(f"  {label:<36} {value}")


def _print_summary(
    csv_name: str,
    fmt: str,
    n_parsed: int,
    n_intra_doi: int,
    n_intra_title: int,
    n_already_doi: int,
    n_already_title: int,
    mech_passed: int,
    mech_rejected: int,
    mech_breakdown: dict,
    floor_discarded: int,
    eval_stats: dict | None,
    n_final: int,
    chroma_stats: dict,
    master_stats: dict,
    n_bib: int,
    bib_path: Path,
) -> None:
    n_removed = n_intra_doi + n_intra_title + n_already_doi + n_already_title
    print(f"\n{'═' * (W + 4)}")
    print("  RESUMEN IMPORT CSV")
    print(f"{'═' * (W + 4)}")
    _row("Archivo:", csv_name)
    _row("Formato:", fmt.upper())
    _hline()
    _row("Registros en CSV:", n_parsed)
    _row("Duplicados intra-CSV (DOI):", n_intra_doi)
    if n_intra_title:
        _row("Duplicados intra-CSV (título):", n_intra_title)
    _row("Ya en master_db (DOI):", n_already_doi)
    if n_already_title:
        _row("Ya en master_db (título similar):", n_already_title)
    _row("A procesar:", n_parsed - n_removed)
    _hline()
    _row("Pasaron filtro mecánico:", mech_passed)
    _row("Rechazados mecánicos:", mech_rejected)
    for reason, n in sorted(mech_breakdown.items(), key=lambda x: -x[1]):
        print(f"    {reason:<32} {n}")
    _row("Descartados por citation floor:", floor_discarded)
    if eval_stats:
        _hline()
        _row("Evaluados:", eval_stats["total"])
        for cat in (
            "relevante", "potencialmente_relevante",
            "descartado_semantica", "no_relevante", "error",
        ):
            n = eval_stats.get(cat, 0)
            if n:
                print(f"    {cat:<32} {n}")
    _hline()
    _row("Papers insertados (finales):", n_final)
    _row("ChromaDB  +nuevos / ya existían:", f"{chroma_stats['added']} / {chroma_stats['skipped']}")
    _row("Master DB +nuevos:", master_stats["added"])
    _row(f"BibTeX ({n_bib} entradas) →", str(bib_path))
    print(f"{'═' * (W + 4)}\n")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def load_config(path: str = "config.yaml") -> dict:
    """Load YAML configuration. Same file as search.py so thresholds stay consistent."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    """
    Import a Scopus or WoS CSV into a project using the same filter pipeline as search.py.

    Stages:
    1.  Parse CSV (auto-detect encoding and delimiter).
    2.  Detect format (Scopus vs WoS) from column signatures.
    3.  Normalize rows to the internal paper schema.
    4.  Intra-CSV deduplication by DOI, then by title similarity.
    5.  Skip papers already in master_db (DOI + title checks).
    6.  Mechanical filter (abstract / DOI / citation count).
    7.  Citation floor.
    8.  Optional embedding evaluation when --context is provided.
    9.  Insert accepted papers into ChromaDB and master papers.json.
    10. Regenerate master.bib and save an import log under sessions/.
    """
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Import a Scopus or WoS CSV export into a project"
    )
    parser.add_argument("--project", required=True, help="Project name")
    parser.add_argument("--file",    required=True, help="Path to the CSV/TSV file")
    parser.add_argument(
        "--context", default=None,
        help="Research context for semantic evaluation. "
             "When omitted, all papers that pass filters are imported.",
    )
    parser.add_argument("--min-cit-pre2015", type=int, default=None,
                        help="Override min citations for papers with year < 2015")
    parser.add_argument("--min-cit-mid",     type=int, default=None,
                        help="Override min citations for papers 2015–2020")
    parser.add_argument("--min-semantic",    type=float, default=None,
                        help="Override min semantic score (default from config)")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    config    = load_config(args.config)
    flt_cfg   = config["filters"]
    floor_cfg = dict(config["citation_floors"])  # mutable copy for overrides
    ev_cfg    = config["evaluation"]
    emb_model = config["embeddings"]["model"]

    if args.min_cit_pre2015 is not None:
        floor_cfg["pre_2015"]["min_citations"] = args.min_cit_pre2015
    if args.min_cit_mid is not None:
        floor_cfg["mid_range"]["min_citations"] = args.min_cit_mid

    pm = ProjectManager(config["storage"]["projects_dir"])
    pm.init_project(args.project)

    csv_path = Path(args.file).resolve()
    if not csv_path.exists():
        print(f"[!] Archivo no encontrado: {csv_path}")
        sys.exit(1)

    # ── Header ────────────────────────────────────────────────────────────
    print(f"\n{'═' * (W + 4)}")
    print(f"  CSV IMPORT  —  proyecto: {args.project}")
    print(f"  Archivo: {csv_path.name}")
    print(f"{'═' * (W + 4)}")

    # ── Parse ─────────────────────────────────────────────────────────────
    try:
        rows = _read_csv(csv_path)
    except ValueError as exc:
        print(f"[!] {exc}")
        sys.exit(1)

    if not rows:
        print("[!] El archivo CSV está vacío.")
        sys.exit(1)

    try:
        fmt = _detect_format(set(rows[0].keys()))
    except ValueError as exc:
        print(f"[!] {exc}")
        sys.exit(1)

    col_map = _SCOPUS_COLS if fmt == "scopus" else _WOS_COLS
    print(f"\n  Formato detectado : {fmt.upper()}")
    print(f"  Registros leídos  : {len(rows)}")
    logger.info(f"CSV format: {fmt} | rows: {len(rows)}")

    papers_raw = [
        _normalize_paper(row, col_map, fmt, str(csv_path))
        for row in rows
    ]

    # ── Stage 1: intra-CSV dedup by DOI ──────────────────────────────────
    papers_deduped, n_intra_doi = deduplicate_by_doi(papers_raw)
    logger.info(f"Intra-CSV DOI dedup: {len(papers_deduped)} unique, {n_intra_doi} removed")

    # ── Stage 1b: intra-CSV dedup by title similarity ─────────────────────
    papers_deduped, n_intra_title = deduplicate_by_title(papers_deduped)
    logger.info(f"Intra-CSV title dedup: {n_intra_title} near-duplicate titles removed")

    # ── Stage 2: filter out papers already in master_db ──────────────────
    master_all = pm.get_all_master_papers(args.project)
    known_dois = {
        ((p.get("externalIds") or {}).get("DOI") or "").strip().lower()
        for p in master_all
        if ((p.get("externalIds") or {}).get("DOI") or "").strip()
    }
    papers_new, n_already_doi = _filter_known(papers_deduped, known_dois)
    master_titles_existing = [p.get("title") or "" for p in master_all]
    papers_new, n_already_title = filter_known_by_title(papers_new, master_titles_existing)
    logger.info(
        f"Master-DB pre-check: {n_already_doi} by DOI + {n_already_title} by title already present, "
        f"{len(papers_new)} new to process"
    )

    if not papers_new:
        print(
            "\n  Todos los papers del CSV ya están en la master_db. "
            "Nada que insertar."
        )
        _print_summary(
            csv_path.name, fmt, len(rows),
            n_intra_doi, n_intra_title,
            n_already_doi, n_already_title,
            0, 0, {}, 0, None, 0,
            {"added": 0, "skipped": 0}, {"added": 0, "skipped": 0},
            len(pm.get_all_master_papers(args.project)),
            pm.bibtex_path(args.project),
        )
        sys.exit(0)

    # ── Stage 3: mechanical filter ────────────────────────────────────────
    mech_passed, mech_rejected = apply_filter(
        papers_new,
        require_abstract=flt_cfg["require_abstract"],
        require_doi=flt_cfg["require_doi"],
        require_citation_count=flt_cfg["require_citation_count"],
    )
    mech_breakdown: dict[str, int] = {}
    for p in mech_rejected:
        for r in p.get("filter_reasons", []):
            mech_breakdown[r] = mech_breakdown.get(r, 0) + 1
    logger.info(f"Mechanical filter: {len(mech_passed)} passed, {len(mech_rejected)} rejected")

    # ── Stage 4: citation floor ───────────────────────────────────────────
    floor_passed, floor_discarded = apply_citation_floor(mech_passed, floor_cfg)
    floor_passed.sort(key=lambda p: p.get("citationCount") or 0, reverse=True)
    logger.info(
        f"Citation floor: {len(floor_passed)} passed, "
        f"{len(floor_discarded)} discarded"
    )

    # ── Stage 5: optional embedding evaluation ────────────────────────────
    final_papers = floor_passed
    eval_stats: dict | None = None

    if args.context and floor_passed:
        thr = ev_cfg["thresholds"]
        w   = ev_cfg["weights"]
        min_sem = (
            args.min_semantic
            if args.min_semantic is not None
            else thr["min_semantic"]
        )
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
            if (p.get("evaluation") or {}).get("category")
            in ("relevante", "potencialmente_relevante")
        ]
        logger.info(f"After evaluation: {len(final_papers)} papers accepted")

    if not final_papers:
        print("\n  Ningún paper pasó todos los filtros. No se insertó nada.")
        _print_summary(
            csv_path.name, fmt, len(rows),
            n_intra_doi, n_intra_title,
            n_already_doi, n_already_title,
            len(mech_passed), len(mech_rejected), mech_breakdown,
            len(floor_discarded), eval_stats, 0,
            {"added": 0, "skipped": 0}, {"added": 0, "skipped": 0},
            len(pm.get_all_master_papers(args.project)),
            pm.bibtex_path(args.project),
        )
        sys.exit(0)

    # ── Stage 6: insert into ChromaDB ─────────────────────────────────────
    chroma = MasterVectorDB(
        persist_dir=pm.chroma_dir(args.project),
        model_name=emb_model,
    )
    chroma_stats = chroma.upsert_papers(final_papers)
    logger.info(
        f"ChromaDB: +{chroma_stats['added']} new, "
        f"{chroma_stats['skipped']} already present"
    )

    # ── Stage 7: update master papers.json ───────────────────────────────
    master_stats = pm.upsert_master_papers(args.project, final_papers)
    logger.info(f"Master DB: +{master_stats['added']} new papers added")

    # ── Stage 8: regenerate BibTeX ────────────────────────────────────────
    all_papers = pm.get_all_master_papers(args.project)
    bib_path   = pm.bibtex_path(args.project)
    n_bib      = export_bibtex(all_papers, bib_path)
    logger.info(f"BibTeX: {n_bib} entries → {bib_path}")

    # ── Stage 9: save import log in sessions/ ────────────────────────────
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_path = (
        pm.project_path(args.project) / "sessions" / f"{ts}_csv_import"
    )
    session_path.mkdir(parents=True, exist_ok=True)
    _save_import_log(session_path, {
        "type":                 "csv_import",
        "project":              args.project,
        "csv_file":             str(csv_path),
        "format":               fmt,
        "n_parsed":             len(rows),
        "n_intra_doi":          n_intra_doi,
        "n_intra_title":        n_intra_title,
        "n_already_doi":        n_already_doi,
        "n_already_title":      n_already_title,
        "n_mech_passed":        len(mech_passed),
        "n_mech_rejected":      len(mech_rejected),
        "mech_breakdown":       mech_breakdown,
        "n_floor_discarded":    len(floor_discarded),
        "eval_stats":           eval_stats,
        "n_final":              len(final_papers),
        "chroma_stats":         chroma_stats,
        "master_stats":         master_stats,
        "context_used":         bool(args.context),
    })

    # ── Summary ───────────────────────────────────────────────────────────
    _print_summary(
        csv_path.name, fmt, len(rows),
        n_intra_doi, n_intra_title,
        n_already_doi, n_already_title,
        len(mech_passed), len(mech_rejected), mech_breakdown,
        len(floor_discarded), eval_stats, len(final_papers),
        chroma_stats, master_stats, n_bib, bib_path,
    )


if __name__ == "__main__":
    main()
