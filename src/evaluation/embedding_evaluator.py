import logging
import math
from typing import Optional

import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


def _log_citation_score(citation_count: int | None, ref: float) -> float:
    """
    Log-normalized citation impact score in [0, 1].

    Uses log1p so:
      - 0 cites   → 0.0
      - ref cites → 1.0  (saturates here)
      - >ref cites → capped at 1.0

    The log scale makes the gap 0→100 much larger than 1000→1100,
    which is the intended behaviour for academic impact.
    """
    c = max(0, citation_count or 0)
    return min(math.log1p(c) / math.log1p(ref), 1.0)


class EmbeddingEvaluator:
    """
    Scores each paper with a weighted combination of:
      - semantic similarity  (cosine distance, context ↔ title+abstract)
      - citation impact      (log-normalised citationCount)

    Pipeline per paper:
      1. If semantic_score < min_semantic → category "descartado_semantica", skip combined score.
      2. Otherwise: final_score = w_semantic * sem_score + w_impact * impact_score
      3. Classify final_score against relevant / potentially thresholds.

    Model loads lazily; context embedding is cached within a session.
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        min_semantic: float = 0.40,
        threshold_relevant: float = 0.50,
        threshold_potentially: float = 0.30,
        weight_semantic: float = 0.70,
        weight_impact: float = 0.30,
        citation_ref: float = 1000.0,
    ):
        self._model_name = model_name
        self._min_semantic = min_semantic
        self._t_relevant = threshold_relevant
        self._t_potentially = threshold_potentially
        self._w_sem = weight_semantic
        self._w_imp = weight_impact
        self._citation_ref = citation_ref
        self._model: Optional[SentenceTransformer] = None
        self._cached_context: Optional[str] = None
        self._context_emb: Optional[np.ndarray] = None

    def _load_model(self) -> SentenceTransformer:
        if self._model is None:
            logger.info(f"Loading embedding model: {self._model_name}")
            self._model = SentenceTransformer(self._model_name)
        return self._model

    def _context_embedding(self, context: str) -> np.ndarray:
        """Return the embedding for the research context, recomputing only if the context changed."""
        if self._cached_context != context:
            self._cached_context = context
            self._context_emb = self._load_model().encode(context, convert_to_numpy=True)
        return self._context_emb  # type: ignore[return-value]

    def _classify(self, score: float) -> str:
        """Map a numeric combined score to a human-readable relevance category."""
        if score >= self._t_relevant:
            return "relevante"
        if score >= self._t_potentially:
            return "potencialmente_relevante"
        return "no_relevante"

    def evaluate_batch(self, papers: list[dict], context: str) -> list[dict]:
        """
        Score all papers in one vectorized pass for efficiency.

        All paper texts are encoded in a single model.encode() call (batch
        inference), then cosine similarity is computed with a matrix multiply
        against the context embedding. This is much faster than scoring papers
        one at a time, especially for batches of 100+.
        """
        if not papers:
            return []

        model = self._load_model()
        ctx_emb = self._context_embedding(context)

        texts = [
            f"{p.get('title') or ''} {p.get('abstract') or ''}".strip()
            for p in papers
        ]
        logger.info(f"Encoding {len(texts)} papers with {self._model_name}...")
        paper_embs = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)

        # Vectorised cosine similarity
        ctx_norm = ctx_emb / (np.linalg.norm(ctx_emb) + 1e-10)
        paper_norms = paper_embs / (np.linalg.norm(paper_embs, axis=1, keepdims=True) + 1e-10)
        sem_scores: np.ndarray = paper_norms @ ctx_norm  # shape (n,)

        results = []
        for paper, sem in zip(papers, sem_scores.tolist()):
            if sem < self._min_semantic:
                results.append({
                    **paper,
                    "evaluation": {
                        "category": "descartado_semantica",
                        "score": round(sem, 4),
                        "semantic_score": round(sem, 4),
                        "impact_score": 0.0,
                        "reasoning": (
                            f"semantic_score={sem:.4f} < min_semantic={self._min_semantic}"
                        ),
                    },
                })
                continue

            imp = _log_citation_score(paper.get("citationCount"), self._citation_ref)
            final = self._w_sem * sem + self._w_imp * imp
            results.append({
                **paper,
                "evaluation": {
                    "category": self._classify(final),
                    "score": round(final, 4),
                    "semantic_score": round(sem, 4),
                    "impact_score": round(imp, 4),
                    "reasoning": (
                        f"score={final:.4f} "
                        f"(semantic={sem:.4f}x{self._w_sem} + "
                        f"impact={imp:.4f}x{self._w_imp})"
                    ),
                },
            })
        return results
