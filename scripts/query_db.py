#!/usr/bin/env python3
"""Ask a natural-language question (Spanish or English) over a project's library.

    python scripts/query_db.py --project tesis --question "¿Qué métodos no supervisados se usan?" --top 10
"""
import argparse

from _common import get_config

from src.pipeline import semantic_query

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--project", required=True)
ap.add_argument("--question", required=True)
ap.add_argument("--top", type=int, default=10)
a = ap.parse_args()
for r in semantic_query(a.project, a.question, a.top, get_config()):
    print(f"{r['rank']:>3}. [{r['similarity']:.3f}] {r['title']} ({r['year']}) {r['doi'] or ''}")
