#!/usr/bin/env python3
"""Import a Scopus / Web of Science / Zotero CSV export into a project.

    python scripts/import_csv.py --project tesis --file scopus.csv [--context "..."]
"""
import argparse

from _common import get_config, print_event

from src.pipeline import run_import

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--project", required=True)
ap.add_argument("--file", required=True)
ap.add_argument("--context", help="Research context (stored in the project; omit to reuse it)")
a = ap.parse_args()
run_import(a.project, a.file, a.context, get_config(), print_event)
