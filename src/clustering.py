"""
Thematic clustering of the library: K-Means over the cached embeddings, k picked
with the elbow (max perpendicular distance) method, clusters labelled with KeyBERT.
"""
from datetime import datetime
from typing import Callable

import numpy as np

from src.embeddings.model import get_embedder
from src.embeddings.store import EmbeddingStore
from src.keywords import label_from_keywords
from src.storage.project_manager import ProjectManager, _write_json


def find_elbow(inertias: list[float]) -> int:
    if len(inertias) <= 2:
        return 0
    xs = np.linspace(0.0, 1.0, len(inertias))
    lo, hi = min(inertias), max(inertias)
    ys = np.array([(v - lo) / max(hi - lo, 1e-12) for v in inertias])
    dx, dy = xs[-1] - xs[0], ys[-1] - ys[0]
    dists = np.abs(dy * (xs[0] - xs) - dx * (ys[0] - ys)) / (np.hypot(dx, dy) + 1e-12)
    return int(np.argmax(dists))


def run_clustering(project: str, config: dict, emit: Callable[[dict], None],
                   k_min: int = 2, k_max: int = 8, top_kw: int = 5,
                   only_categories: list[str] | None = None) -> dict:
    from keybert import KeyBERT
    from sklearn.cluster import KMeans

    pm = ProjectManager(config["storage"]["projects_dir"])
    embedder = get_embedder(config)
    with pm.lock(project):
        papers = pm.get_papers(project)
        if only_categories:
            papers = [p for p in papers if (p.get("evaluation") or {}).get("category") in only_categories]
        if len(papers) < 3:
            raise ValueError("Need at least 3 papers to cluster.")
        X = EmbeddingStore(pm.embeddings_path(project), embedder).vectors_for(papers)
    emit({"type": "loaded", "count": len(papers)})

    k_min = max(2, k_min)
    k_max = max(k_min, min(k_max, len(papers) - 1))
    emit({"type": "elbow_start", "k_min": k_min, "k_max": k_max})
    ks, inertias, models = list(range(k_min, k_max + 1)), [], []
    for k in ks:
        km = KMeans(n_clusters=k, random_state=42, n_init=10).fit(X)
        inertias.append(float(km.inertia_))
        models.append(km)
        emit({"type": "elbow_step", "k": k, "inertia": round(float(km.inertia_), 3)})
    best = find_elbow(inertias)
    best_k, labels = ks[best], models[best].labels_
    emit({"type": "clustered", "k": best_k, "num_clusters": best_k})

    emit({"type": "labeling"})
    kw_model = None
    groups = [[papers[i] for i in np.where(labels == cid)[0]] for cid in range(best_k)]
    # Preferred: distinctive per-paper keyphrases (already computed, comparable across clusters).
    from_keywords = label_from_keywords(groups, n=top_kw)
    clusters = []
    for cid, members in enumerate(groups):
        phrases = from_keywords[cid]
        if len(phrases) < 2:  # papers without keywords (old libraries) -> KeyBERT on the cluster text
            kw_model = kw_model or KeyBERT(model=embedder.model)
            text = " ".join(f"{p.get('title') or ''}. {p.get('abstract') or ''}" for p in members)[:20000]
            kws = kw_model.extract_keywords(text, keyphrase_ngram_range=(1, 3), stop_words="english",
                                            use_mmr=True, diversity=0.5, top_n=top_kw)
            phrases = [kw for kw, _ in kws]
        members.sort(key=lambda p: (p.get("evaluation") or {}).get("score") or 0, reverse=True)
        clusters.append({
            "id": cid,
            "label": " · ".join(phrases[:3]) or f"Cluster {cid}",
            "keyphrases": phrases,
            "paper_count": len(members),
            "paper_ids": [p["id"] for p in members],
            "top_titles": [p.get("title") for p in members[:5]],
        })
    clusters.sort(key=lambda c: c["paper_count"], reverse=True)

    # 2-D map of the library (t-SNE on the same embeddings), scaled to 0..1
    emit({"type": "mapping"})
    from sklearn.manifold import TSNE
    perplexity = float(max(2, min(30, (len(papers) - 1) // 3)))
    xy = TSNE(n_components=2, perplexity=perplexity, init="pca", metric="cosine",
              random_state=42).fit_transform(X)
    xy = (xy - xy.min(axis=0)) / np.maximum(xy.max(axis=0) - xy.min(axis=0), 1e-9)
    points = [{"id": p["id"], "x": round(float(x), 4), "y": round(float(y), 4), "cluster": int(c)}
              for p, (x, y), c in zip(papers, xy, labels)]
    report = {
        "project": project, "generated_at": datetime.now().isoformat(),
        "model": embedder.name, "total_papers": len(papers), "num_clusters": best_k,
        "only_categories": only_categories,
        "inertia_curve": list(zip(ks, [round(v, 3) for v in inertias])), "clusters": clusters,
        "points": points,
    }
    _write_json(pm.clusters_path(project), report)
    emit({"type": "done", "num_clusters": best_k})
    return report
