#!/usr/bin/env python3
"""
Semantic similarity search over the project's master ChromaDB.

Usage:
    python scripts/query_db.py --project <name> --question "natural language query"
                                [--top N]  (default: 5)
"""
import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.embeddings.chroma_store import MasterVectorDB
from src.storage.project_manager import ProjectManager


def load_config(path: str = "config.yaml") -> dict:
    """Load YAML configuration to get the embedding model name and projects directory."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _abstract_preview(abstract: str, max_chars: int = 220) -> str:
    """Truncate the abstract to a readable preview, cutting at a word boundary."""
    if not abstract:
        return "(no abstract)"
    text = abstract.strip()
    if len(text) <= max_chars:
        return text
    # cut at last space before limit
    cut = text[:max_chars].rsplit(" ", 1)[0]
    return cut + " …"


def main() -> None:
    """
    Embed the question with the same model used during ingestion and retrieve
    the top-N papers by cosine similarity from ChromaDB. Useful for exploring
    the library with natural-language questions without the web UI.
    """
    parser = argparse.ArgumentParser(description="Semantic search over project papers")
    parser.add_argument("--project", required=True, help="Project name")
    parser.add_argument("--question", required=True, help="Natural language query")
    parser.add_argument("--top", type=int, default=5, help="Number of results (default: 5)")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    pm = ProjectManager(config["storage"]["projects_dir"])
    chroma_dir = pm.chroma_dir(args.project)

    if not chroma_dir.exists():
        print(f"[!] No ChromaDB found for project '{args.project}'.")
        print(f"    Expected at: {chroma_dir}")
        print("    Run the pipeline first with --context to populate it.")
        sys.exit(1)

    emb_model = config["embeddings"]["model"]
    db = MasterVectorDB(persist_dir=chroma_dir, model_name=emb_model)

    total = db.count()
    if total == 0:
        print(f"[!] The ChromaDB for project '{args.project}' is empty.")
        sys.exit(1)

    print(f"\nSearching in '{args.project}' ({total} papers indexed)")
    print(f"Question: {args.question}\n")
    print("─" * 70)

    results = db.query(args.question, n_results=args.top)

    if not results:
        print("No results found.")
        sys.exit(0)

    for r in results:
        doi_str = f"DOI:{r['doi']}" if r["doi"] else "DOI:—"
        venue_str = f"  {r['venue']}" if r["venue"] else ""
        category_str = f"  [{r['category']}]" if r["category"] else ""
        print(
            f"#{r['rank']}  score={r['score']:.4f}  "
            f"[{r['year'] or '?'}]  cites={r['citationCount'] or '?'}"
            f"{category_str}"
        )
        print(f"    {r['title']}")
        print(f"    {doi_str}{venue_str}")
        print(f"    {_abstract_preview(r['abstract'])}")
        print()


if __name__ == "__main__":
    main()
