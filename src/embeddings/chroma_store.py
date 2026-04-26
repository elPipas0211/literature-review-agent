import hashlib
import logging
from pathlib import Path
from typing import Optional

from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


def _get_doi(paper: dict) -> Optional[str]:
    """Extract and normalize the DOI from the nested externalIds field."""
    doi = ((paper.get("externalIds") or {}).get("DOI") or "").strip().lower()
    return doi if doi else None


def _make_id(paper: dict) -> str:
    """
    Derive a stable ChromaDB document ID for a paper.

    DOI is used when available because it's globally unique. For papers
    without a DOI (some conference papers, preprints), we fall back to
    an MD5 hash of title+year so re-imports of the same paper still match.
    """
    doi = _get_doi(paper)
    if doi:
        return doi
    raw = f"{(paper.get('title') or '')}_{paper.get('year', '')}"
    return "noDOI_" + hashlib.md5(raw.encode()).hexdigest()[:12]


def _truncate(text: str, max_chars: int = 5000) -> str:
    """Guard against extremely long abstracts that would slow down embedding or exceed ChromaDB limits."""
    return text[:max_chars] if text else ""


class MasterVectorDB:
    """
    Persistent ChromaDB vector store for the master paper collection.

    Layout: projects/<project>/master_db/embeddings/
    Collection: "papers"
    IDs: normalized DOI (or title hash for papers without DOI)
    """

    COLLECTION = "papers"

    def __init__(self, persist_dir: str | Path, model_name: str = "all-MiniLM-L6-v2"):
        import chromadb
        self._persist_dir = Path(persist_dir)
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._model_name = model_name
        self._model: Optional[SentenceTransformer] = None
        self._client = chromadb.PersistentClient(path=str(self._persist_dir))
        self._collection = self._client.get_or_create_collection(
            self.COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )

    def _load_model(self) -> SentenceTransformer:
        if self._model is None:
            logger.info(f"Loading embedding model: {self._model_name}")
            self._model = SentenceTransformer(self._model_name)
        return self._model

    def _existing_ids(self) -> set[str]:
        """Fetch all document IDs in one call to enable O(1) duplicate checks before inserting."""
        if self._collection.count() == 0:
            return set()
        return set(self._collection.get(include=[])["ids"])

    def upsert_papers(self, papers: list[dict]) -> dict:
        """
        Insert new papers into the vector DB, skipping those already present by DOI.
        Returns {"added": N, "skipped": M}.
        """
        if not papers:
            return {"added": 0, "skipped": 0}

        existing = self._existing_ids()
        to_add: list[tuple[str, dict]] = []
        skipped = 0

        for paper in papers:
            pid = _make_id(paper)
            if pid in existing:
                skipped += 1
            else:
                to_add.append((pid, paper))

        if not to_add:
            return {"added": 0, "skipped": skipped}

        model = self._load_model()
        texts = [
            _truncate(f"{p.get('title') or ''} {p.get('abstract') or ''}".strip())
            for _, p in to_add
        ]
        embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)

        ids = [pid for pid, _ in to_add]
        metas = []
        for _, paper in to_add:
            ev = paper.get("evaluation") or {}
            metas.append({
                "title": _truncate(paper.get("title") or "", 500),
                "year": int(paper.get("year") or 0),
                "citationCount": int(paper.get("citationCount") or 0),
                "doi": ((paper.get("externalIds") or {}).get("DOI") or ""),
                "abstract": _truncate(paper.get("abstract") or "", 1000),
                "venue": _truncate(paper.get("venue") or "", 200),
                "category": ev.get("category") or "unknown",
                "eval_score": float(ev.get("score") or 0.0),
            })

        self._collection.add(
            ids=ids,
            embeddings=embeddings.tolist(),
            documents=texts,
            metadatas=metas,
        )
        return {"added": len(to_add), "skipped": skipped}

    def count(self) -> int:
        return self._collection.count()

    def query(self, text: str, n_results: int = 5) -> list[dict]:
        """
        Semantic similarity search. Returns results sorted by similarity (desc).
        Each entry: rank, title, year, citationCount, doi, abstract, venue, category, score.
        """
        total = self._collection.count()
        if total == 0:
            return []

        model = self._load_model()
        q_emb = model.encode(text, convert_to_numpy=True)

        results = self._collection.query(
            query_embeddings=[q_emb.tolist()],
            n_results=min(n_results, total),
            include=["metadatas", "distances"],
        )

        out = []
        for i, (meta, dist) in enumerate(
            zip(results["metadatas"][0], results["distances"][0])
        ):
            # cosine space: distance = 1 - similarity → similarity = 1 - distance
            similarity = round(max(0.0, 1.0 - dist), 4)
            out.append({
                "rank": i + 1,
                "title": meta.get("title", ""),
                "year": meta.get("year"),
                "citationCount": meta.get("citationCount"),
                "doi": meta.get("doi", ""),
                "abstract": meta.get("abstract", ""),
                "venue": meta.get("venue", ""),
                "category": meta.get("category", ""),
                "score": similarity,
            })
        return out
