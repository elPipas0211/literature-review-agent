#!/usr/bin/env python3
"""
Cluster master-DB papers with K-Means (elbow method selects k automatically)
and label each cluster using KeyBERT keyphrases from titles + abstracts.

Usage:
    python scripts/cluster.py --project <name>
                               [--k-min INT]    min clusters to try (default: 2)
                               [--k-max INT]    max clusters to try (default: 8)
                               [--top-kw INT]   keyphrases per cluster (default: 5)
                               [--config FILE]  (default: config.yaml)
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.storage.project_manager import ProjectManager


def _load_config(path: str) -> dict:
    """Load YAML configuration to get the embedding model name and projects directory."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _fetch_all(chroma_dir: Path) -> tuple[list, list]:
    """
    Pull all stored embeddings and metadata from ChromaDB in one batch.

    ChromaDB's get() is more efficient than query() for full collection retrieval
    because it skips the ANN search step.
    """
    import chromadb
    client = chromadb.PersistentClient(path=str(chroma_dir))
    col = client.get_or_create_collection(
        "papers", metadata={"hnsw:space": "cosine"}
    )
    if col.count() == 0:
        return [], []
    result = col.get(include=["embeddings", "metadatas"])
    return result["embeddings"], result["metadatas"]


def _find_elbow(inertias: list[float]) -> int:
    """0-based index of the elbow using max perpendicular distance from the line
    connecting the first and last points of the inertia curve."""
    if len(inertias) <= 1:
        return 0
    n = len(inertias)
    xs = np.linspace(0.0, 1.0, n)
    y_lo, y_hi = min(inertias), max(inertias)
    span = max(y_hi - y_lo, 1e-12)
    ys = np.array([(v - y_lo) / span for v in inertias])
    x1, y1 = xs[0], ys[0]
    x2, y2 = xs[-1], ys[-1]
    dx, dy = x2 - x1, y2 - y1
    denom = (dx**2 + dy**2) ** 0.5 + 1e-12
    dists = [abs(dy * (x1 - x) - dx * (y1 - y)) / denom
             for x, y in zip(xs, ys)]
    return int(np.argmax(dists))


def _kmeans_elbow(X: np.ndarray, k_min: int, k_max: int):
    """
    Fit K-Means for each k in [k_min, k_max] and return the model at the elbow.

    Trying all k values (rather than a binary search) keeps the code simple and
    the range is small enough (default 2–8) that the overhead is negligible.
    """
    from sklearn.cluster import KMeans

    ks = list(range(k_min, k_max + 1))
    inertias: list[float] = []
    models: list = []
    for k in ks:
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        km.fit(X)
        inertias.append(float(km.inertia_))
        models.append(km)
        print(f"    k={k}  inertia={km.inertia_:.2f}")

    best_idx = _find_elbow(inertias)
    best_k = ks[best_idx]
    return models[best_idx].labels_, best_k, ks, inertias


def _extract_keyphrases(combined_text: str, kw_model, top_n: int) -> list[str]:
    """
    Extract the most representative n-gram keyphrases from a cluster's combined text.

    MMR (Maximal Marginal Relevance) with diversity=0.5 avoids returning near-duplicate
    phrases that all say the same thing in slightly different words.
    """
    kws = kw_model.extract_keywords(
        combined_text[:8000],
        keyphrase_ngram_range=(1, 3),
        stop_words="english",
        use_mmr=True,
        diversity=0.5,
        top_n=top_n,
    )
    return [kw for kw, _ in kws]


def main() -> None:
    """
    Group all master-DB papers into thematic clusters and label each cluster.

    Uses the pre-computed embeddings already stored in ChromaDB — no re-encoding
    is needed. The elbow method selects k automatically so the user doesn't have
    to guess. Saves results to clusters.json for the frontend to consume.
    """
    parser = argparse.ArgumentParser(
        description="Cluster project papers with K-Means (elbow) + KeyBERT labels"
    )
    parser.add_argument("--project",  required=True,  help="Project name")
    parser.add_argument("--k-min",   type=int, default=2, help="Min clusters to try (default: 2)")
    parser.add_argument("--k-max",   type=int, default=8, help="Max clusters to try (default: 8)")
    parser.add_argument("--top-kw",  type=int, default=5, help="Keyphrases per cluster (default: 5)")
    parser.add_argument("--config",  default="config.yaml")
    args = parser.parse_args()

    config = _load_config(args.config)
    model_name = config["embeddings"]["model"]
    pm = ProjectManager(config["storage"]["projects_dir"])
    chroma_dir = pm.chroma_dir(args.project)

    if not chroma_dir.exists():
        print(f"[!] No ChromaDB found for project '{args.project}'.")
        sys.exit(1)

    # ── 1. load embeddings ────────────────────────────────────────────────
    print(f"\nLoading embeddings for project '{args.project}'...")
    embeddings, metadatas = _fetch_all(chroma_dir)
    n = len(embeddings)
    if n == 0:
        print("[!] ChromaDB is empty. Nothing to cluster.")
        sys.exit(1)
    print(f"    {n} papers loaded.")

    # ── 2. K-Means with elbow ─────────────────────────────────────────────
    k_min = max(2, args.k_min)
    k_max = min(args.k_max, n)
    X = np.array(embeddings, dtype=np.float32)
    print(f"Running K-Means elbow (k={k_min}…{k_max})...")
    labels, best_k, ks, inertias = _kmeans_elbow(X, k_min, k_max)
    print(f"    Elbow at k={best_k}.")

    # ── 3. KeyBERT model ──────────────────────────────────────────────────
    print("Loading KeyBERT model...")
    from keybert import KeyBERT
    from sentence_transformers import SentenceTransformer
    kw_model = KeyBERT(model=SentenceTransformer(model_name))

    # ── 4. build cluster data ─────────────────────────────────────────────
    clusters_out = []
    for cid in range(best_k):
        idxs = [i for i, lbl in enumerate(labels) if lbl == cid]
        metas = [metadatas[i] for i in idxs]
        combined = " ".join(
            f"{m.get('title', '')} {m.get('abstract', '')}" for m in metas
        )
        keyphrases = _extract_keyphrases(combined, kw_model, args.top_kw)
        label = " | ".join(keyphrases[:3]) if keyphrases else f"Cluster {cid}"

        papers = sorted(
            [{"title": m.get("title", ""), "year": m.get("year"),
              "doi": m.get("doi", ""), "citationCount": m.get("citationCount"),
              "venue": m.get("venue", ""), "category": m.get("category", "")}
             for m in metas],
            key=lambda p: p.get("citationCount") or 0, reverse=True,
        )
        clusters_out.append({
            "id": cid, "label": label, "keyphrases": keyphrases,
            "paper_count": len(papers), "papers": papers,
        })

    clusters_out.sort(key=lambda c: c["paper_count"], reverse=True)

    # ── 5. terminal output ────────────────────────────────────────────────
    sep = "=" * 70
    print(f"\n{sep}")
    print(f"CLUSTER REPORT  —  {args.project}  (K-Means, k={best_k})")
    print(f"Total: {n} papers  |  Clusters: {best_k}")
    print(sep)

    for c in clusters_out:
        print(f"\n[Cluster {c['id']}]  {c['label']}")
        print(f"  {c['paper_count']} paper(s)  —  keyphrases: {', '.join(c['keyphrases'])}")
        print()
        for p in c["papers"]:
            yr = p.get("year") or "?"
            cit = p.get("citationCount") or 0
            title = (p.get("title") or "(no title)")[:88]
            print(f"    [{yr}] cites={cit:<6}  {title}")

    print(f"\n{sep}")

    # ── 6. save clusters.json ─────────────────────────────────────────────
    output = {
        "project": args.project,
        "generated_at": datetime.now().isoformat(),
        "total_papers": n,
        "num_clusters": best_k,
        "noise_papers": 0,
        "kmeans_params": {"k": best_k, "k_min": k_min, "k_max": k_max},
        "inertia_curve": list(zip(ks, [round(v, 2) for v in inertias])),
        "clusters": clusters_out,
        "noise": [],
    }
    out_path = pm.master_db_path(args.project) / "clusters.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved  →  {out_path}")


if __name__ == "__main__":
    main()
