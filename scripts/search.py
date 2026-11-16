#!/usr/bin/env python3
"""Search OpenAlex and add the results to a project.

    python scripts/search.py --project tesis --query "anomaly detection time series" \
        --context "Detección de anomalías en sensores industriales" --max-results 200 --year-from 2015
"""
import argparse
import sys

from _common import get_config, print_event

from src.pipeline import run_search
from src.sources.openalex import OpenAlexError

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--project", required=True)
ap.add_argument("--query", required=True)
ap.add_argument("--context", help="Research context (stored in the project; omit to reuse it)")
ap.add_argument("--max-results", type=int, default=100, help="Max records (default 100, max 2000)")
ap.add_argument("--year-from", type=int)
ap.add_argument("--year-to", type=int)
a = ap.parse_args()
try:
    run_search(a.project, a.query, a.context, a.max_results, get_config(), print_event,
               year_from=a.year_from, year_to=a.year_to)
except OpenAlexError as exc:
    sys.exit(f"[error] {exc}")
