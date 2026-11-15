#!/usr/bin/env python3
"""Cluster a project's library (K-Means + elbow + KeyBERT labels).

    python scripts/cluster.py --project tesis [--k-min 2 --k-max 10] [--only relevante potencialmente_relevante]
"""
import argparse

from _common import get_config, print_event

from src.clustering import run_clustering

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--project", required=True)
ap.add_argument("--k-min", type=int, default=2)
ap.add_argument("--k-max", type=int, default=8)
ap.add_argument("--top-kw", type=int, default=5)
ap.add_argument("--only", nargs="*", help="Only cluster papers in these categories")
a = ap.parse_args()
report = run_clustering(a.project, get_config(), print_event, a.k_min, a.k_max, a.top_kw, a.only)
for c in report["clusters"]:
    print(f"\n#{c['id']} ({c['paper_count']} papers) {c['label']}")
    for t in c["top_titles"]:
        print(f"   - {t}")
