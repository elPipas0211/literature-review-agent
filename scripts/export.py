#!/usr/bin/env python3
"""Export a project's library and print the PRISMA identification numbers.

    python scripts/export.py --project tesis --format csv --out tesis.csv
    python scripts/export.py --project tesis --prisma
"""
import argparse
from pathlib import Path

from _common import dump, get_config

from src.pipeline import prisma_summary
from src.storage.project_manager import ProjectManager
from src.utils.bibtex_exporter import export_bibtex
from src.utils.exporters import to_csv, to_ris

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--project", required=True)
ap.add_argument("--format", choices=["csv", "ris", "bib"])
ap.add_argument("--out")
ap.add_argument("--prisma", action="store_true")
a = ap.parse_args()
cfg = get_config()
if a.prisma:
    s = prisma_summary(a.project, cfg)
    s.pop("sessions")
    dump(s)
if a.format:
    papers = ProjectManager(cfg["storage"]["projects_dir"]).get_papers(a.project)
    text = {"csv": to_csv, "ris": to_ris, "bib": export_bibtex}[a.format](papers)
    out = Path(a.out or f"{a.project}.{a.format}")
    out.write_text(text, encoding="utf-8")
    print(f"Wrote {len(papers)} records to {out}")
