"""
One shared sentence-transformers model per process.

The model is multilingual (default: intfloat/multilingual-e5-small) so you can
write the research context or questions in Spanish and still match English
papers. E5 models expect "query: " / "passage: " prefixes; they are
configurable in config.yaml so other models can be dropped in.
"""
import logging
import threading

import numpy as np

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_cache: dict[str, "Embedder"] = {}


class Embedder:
    def __init__(self, name: str, query_prefix: str = "", passage_prefix: str = ""):
        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model %s", name)
        self.name = name
        self.query_prefix = query_prefix
        self.passage_prefix = passage_prefix
        self.model = SentenceTransformer(name, device="cpu")
        self._encode_lock = threading.Lock()

    def _encode(self, texts: list[str]) -> np.ndarray:
        with self._encode_lock:
            vecs = self.model.encode(
                texts, batch_size=32, convert_to_numpy=True,
                normalize_embeddings=True, show_progress_bar=False,
            )
        return np.asarray(vecs, dtype=np.float32)

    def encode_passages(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return self._encode([self.passage_prefix + t for t in texts])

    def encode_query(self, text: str) -> np.ndarray:
        return self._encode([self.query_prefix + text])[0]

    @property
    def dim(self) -> int:
        getter = getattr(self.model, "get_embedding_dimension", None) or self.model.get_sentence_embedding_dimension
        return getter()


def get_embedder(config: dict) -> Embedder:
    emb_cfg = config["embeddings"]
    name = emb_cfg["model"]
    with _lock:
        if name not in _cache:
            _cache[name] = Embedder(
                name,
                query_prefix=emb_cfg.get("query_prefix", ""),
                passage_prefix=emb_cfg.get("passage_prefix", ""),
            )
        return _cache[name]
