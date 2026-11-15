"""
Relevance scoring = ranking aid, not a gatekeeper.

    similarity     raw cosine(context, title+abstract) from the embedding model
    semantic_score similarity rescaled to [0, 1] with the model-specific
                   `similarity_range` from config.yaml (E5 models compress
                   cosine values into a narrow band, ~0.75-0.90)
    impact_score   log1p(citations) / log1p(citation_ref), capped at 1
    score          w_sem * semantic_score + w_imp * impact_score
    category       relevante / potencialmente_relevante / no_relevante (labels only)

Every paper stays in the library regardless of its category; the frontend
mirrors this formula so weights/thresholds can be tuned live.
"""
import math

import numpy as np


def impact_score(citations: int | None, ref: float) -> float:
    c = max(0, citations or 0)
    return min(math.log1p(c) / math.log1p(max(ref, 1)), 1.0)


def rescale(similarity: float, lo: float, hi: float) -> float:
    return float(min(1.0, max(0.0, (similarity - lo) / max(hi - lo, 1e-9))))


def classify(score: float, thresholds: dict) -> str:
    if score >= thresholds["relevant"]:
        return "relevante"
    if score >= thresholds["potentially"]:
        return "potencialmente_relevante"
    return "no_relevante"


def score_papers(papers: list[dict], similarities: np.ndarray, ev_cfg: dict) -> None:
    """Attach an `evaluation` dict to every paper (in place)."""
    lo, hi = ev_cfg["similarity_range"]
    w_sem = ev_cfg["weights"]["semantic"]
    w_imp = ev_cfg["weights"]["impact"]
    ref = ev_cfg["citation_ref"]
    for paper, sim in zip(papers, similarities.tolist()):
        sem = rescale(sim, lo, hi)
        imp = impact_score(paper.get("citationCount"), ref)
        score = w_sem * sem + w_imp * imp
        paper["evaluation"] = {
            "similarity": round(sim, 4),
            "semantic_score": round(sem, 4),
            "impact_score": round(imp, 4),
            "score": round(score, 4),
            "category": classify(score, ev_cfg["thresholds"]),
        }
