import hashlib
import json
import uuid
from datetime import datetime
from pathlib import Path


class ProjectManager:
    """
    Manages the on-disk layout:

    projects/
    └── {project}/
        ├── master_db/
        │   ├── papers.json    ← master DB (all accepted papers across sessions)
        │   ├── master.bib     ← BibTeX export (regenerated each pipeline run)
        │   └── embeddings/    ← ChromaDB vector store (persistent)
        └── sessions/
            └── {session_id}/
                ├── session_log.json
                └── results/
                    └── {query_hash}.json
    """

    def __init__(self, projects_dir: str = "projects"):
        self.root = Path(projects_dir)

    # ------------------------------------------------------------------
    # Project helpers
    # ------------------------------------------------------------------

    def project_path(self, project: str) -> Path:
        """Absolute path to the project root directory."""
        return self.root / project

    def master_db_path(self, project: str) -> Path:
        """Path to master_db/ — contains papers.json, master.bib, and the ChromaDB folder."""
        return self.project_path(project) / "master_db"

    def chroma_dir(self, project: str) -> Path:
        """Path to the ChromaDB persistent vector store for this project."""
        return self.master_db_path(project) / "embeddings"

    def bibtex_path(self, project: str) -> Path:
        """Path to the generated BibTeX file (regenerated on every search/import)."""
        return self.master_db_path(project) / "master.bib"

    def papers_db_path(self, project: str) -> Path:
        """Path to papers.json — the canonical source of truth for all accepted papers."""
        return self.master_db_path(project) / "papers.json"

    def init_project(self, project: str) -> Path:
        """Create the project directory tree if it doesn't exist and initialize an empty papers.json."""
        path = self.project_path(project)
        (path / "sessions").mkdir(parents=True, exist_ok=True)
        (path / "master_db" / "embeddings").mkdir(parents=True, exist_ok=True)
        db = self.papers_db_path(project)
        if not db.exists():
            db.write_text("[]", encoding="utf-8")
        return path

    # ------------------------------------------------------------------
    # Master papers DB helpers
    # ------------------------------------------------------------------

    def get_all_master_papers(self, project: str) -> list[dict]:
        """Return all papers in the master DB, or [] if not initialized."""
        db = self.papers_db_path(project)
        if not db.exists():
            return []
        return json.loads(db.read_text(encoding="utf-8"))

    def upsert_master_papers(self, project: str, papers: list[dict]) -> dict:
        """
        Merge new papers into the master papers.json by DOI.
        Papers without DOI are merged by title+year hash.
        Returns {"added": N, "skipped": M}.
        """
        existing = self.get_all_master_papers(project)

        def _doi(p: dict) -> str:
            return ((p.get("externalIds") or {}).get("DOI") or "").strip().lower()

        def _fallback_key(p: dict) -> str:
            raw = f"{(p.get('title') or '').lower()}_{p.get('year', '')}"
            return "noDOI_" + hashlib.md5(raw.encode()).hexdigest()[:12]

        def _key(p: dict) -> str:
            d = _doi(p)
            return d if d else _fallback_key(p)

        seen = {_key(p): p for p in existing}
        added = 0
        skipped = 0

        for paper in papers:
            k = _key(paper)
            if k in seen:
                skipped += 1
            else:
                seen[k] = paper
                added += 1

        db = self.papers_db_path(project)
        db.write_text(
            json.dumps(list(seen.values()), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {"added": added, "skipped": skipped}

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------

    def new_session(self, project: str) -> tuple[str, Path]:
        """Create a timestamped session directory and write an initial session_log.json."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_id = f"{ts}_{uuid.uuid4().hex[:6]}"
        session_path = self.project_path(project) / "sessions" / session_id
        (session_path / "results").mkdir(parents=True, exist_ok=True)
        log = {
            "session_id": session_id,
            "project": project,
            "created_at": datetime.now().isoformat(),
            "queries": [],
        }
        (session_path / "session_log.json").write_text(
            json.dumps(log, indent=2), encoding="utf-8"
        )
        return session_id, session_path

    # ------------------------------------------------------------------
    # Result persistence
    # ------------------------------------------------------------------

    def save_query_results(
        self,
        session_path: Path,
        query: str,
        source: str,
        passed: list[dict],
        rejected: list[dict],
    ) -> Path:
        """Save per-source raw results to disk and append a summary entry to session_log.json."""
        query_hash = hashlib.md5(f"{source}:{query}".encode()).hexdigest()[:8]
        payload = {
            "query": query,
            "source": source,
            "timestamp": datetime.now().isoformat(),
            "total_retrieved": len(passed) + len(rejected),
            "passed_filter": len(passed),
            "filtered_out": len(rejected),
            "papers": passed,
            "rejected": rejected,
        }
        out = session_path / "results" / f"{source}_{query_hash}.json"
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        # Update session log
        log_path = session_path / "session_log.json"
        log = json.loads(log_path.read_text(encoding="utf-8"))
        log["queries"].append(
            {
                "source": source,
                "query": query,
                "timestamp": payload["timestamp"],
                "passed": len(passed),
                "rejected": len(rejected),
                "result_file": out.name,
            }
        )
        log_path.write_text(json.dumps(log, indent=2), encoding="utf-8")

        return out

    def save_consolidated(
        self,
        session_path: Path,
        papers: list[dict],
        stats: dict,
    ) -> Path:
        """Save the final consolidated output for the session."""
        out = session_path / "consolidated.json"
        payload = {
            "timestamp": datetime.now().isoformat(),
            "pipeline_stats": stats,
            "total_final": len(papers),
            "papers": papers,
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return out
