"""
Per-project embedding cache stored as a single .npz file.

Replaces ChromaDB: for a literature-review library (hundreds to a few thousand
papers) brute-force cosine similarity in numpy is instant, and keeping
embeddings keyed by paper id means papers.json stays the single source of truth.
If the configured model changes, the cache is rebuilt automatically.
"""
from pathlib import Path

import numpy as np

from src.embeddings.model import Embedder
from src.utils.records import paper_text


class EmbeddingStore:
    def __init__(self, path: str | Path, embedder: Embedder):
        self.path = Path(path)
        self.embedder = embedder
        self._ids: list[str] = []
        self._vecs = np.zeros((0, embedder.dim), dtype=np.float32)
        self._load()

    def _load(self):
        if not self.path.exists():
            return
        data = np.load(self.path, allow_pickle=False)
        if str(data["model"]) != self.embedder.name or data["vectors"].shape[1] != self.embedder.dim:
            return  # different model -> rebuild lazily
        self._ids = [str(i) for i in data["ids"]]
        self._vecs = data["vectors"].astype(np.float32)

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.stem + ".tmp.npz")
        np.savez(tmp, ids=np.array(self._ids, dtype=str), vectors=self._vecs,
                 model=np.array(self.embedder.name))
        tmp.replace(self.path)

    def vectors_for(self, papers: list[dict]) -> np.ndarray:
        """Return an (n, dim) matrix aligned with `papers`, encoding any missing ones."""
        index = {pid: i for i, pid in enumerate(self._ids)}
        missing = [p for p in papers if p["id"] not in index]
        if missing:
            new = self.embedder.encode_passages([paper_text(p) for p in missing])
            self._ids.extend(p["id"] for p in missing)
            self._vecs = np.vstack([self._vecs, new]) if len(self._vecs) else new
            self._save()
            index = {pid: i for i, pid in enumerate(self._ids)}
        if not papers:
            return np.zeros((0, self.embedder.dim), dtype=np.float32)
        return self._vecs[[index[p["id"]] for p in papers]]

    def similarities(self, text: str, papers: list[dict]) -> np.ndarray:
        """Cosine similarity between a query/context and each paper."""
        if not papers:
            return np.zeros(0, dtype=np.float32)
        q = self.embedder.encode_query(text)
        return self.vectors_for(papers) @ q
