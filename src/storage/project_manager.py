"""
On-disk layout of a project:

projects/<project>/
├── project.json           research context (protocol) + metadata
├── master_db/
│   ├── papers.json        every unique record ever retrieved (source of truth)
│   ├── embeddings.npz     embedding cache keyed by paper id
│   ├── master.bib         BibTeX export, regenerated after every run
│   └── clusters.json      last clustering report
└── sessions/<session_id>/
    ├── session.json       PRISMA record of the run (query, date, counts per source, config)
    └── results/<source>.json   raw records as returned by each source
"""
import json
import re
import threading
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path

_locks: dict[str, threading.RLock] = defaultdict(threading.RLock)
_locks_guard = threading.Lock()

_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


class InvalidProjectName(ValueError):
    pass


def validate_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise InvalidProjectName("Project name cannot be empty")
    if len(name) > 50:
        raise InvalidProjectName("Project name must be 50 characters or fewer")
    if _UNSAFE.search(name) or name.strip(".") == "":
        raise InvalidProjectName('Project name cannot contain \\ / : * ? " < > | or be only dots')
    return name


def _write_json(path: Path, data) -> None:
    """Atomic write: never leaves a half-written papers.json behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


class ProjectManager:
    def __init__(self, projects_dir: str | Path):
        self.root = Path(projects_dir)

    # ── paths ────────────────────────────────────────────────────────────────
    def project_path(self, project: str) -> Path:
        return self.root / validate_name(project)

    def master_db_path(self, project: str) -> Path:
        return self.project_path(project) / "master_db"

    def papers_db_path(self, project: str) -> Path:
        return self.master_db_path(project) / "papers.json"

    def embeddings_path(self, project: str) -> Path:
        return self.master_db_path(project) / "embeddings.npz"

    def bibtex_path(self, project: str) -> Path:
        return self.master_db_path(project) / "master.bib"

    def clusters_path(self, project: str) -> Path:
        return self.master_db_path(project) / "clusters.json"

    def meta_path(self, project: str) -> Path:
        return self.project_path(project) / "project.json"

    def sessions_dir(self, project: str) -> Path:
        return self.project_path(project) / "sessions"

    # ── projects ─────────────────────────────────────────────────────────────
    def exists(self, project: str) -> bool:
        return self.papers_db_path(project).exists()

    def list_projects(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(p.name for p in self.root.iterdir() if (p / "master_db" / "papers.json").exists())

    def init_project(self, project: str) -> Path:
        path = self.project_path(project)
        self.sessions_dir(project).mkdir(parents=True, exist_ok=True)
        self.master_db_path(project).mkdir(parents=True, exist_ok=True)
        if not self.papers_db_path(project).exists():
            _write_json(self.papers_db_path(project), [])
        if not self.meta_path(project).exists():
            _write_json(self.meta_path(project), {"context": "", "created_at": datetime.now().isoformat()})
        return path

    def lock(self, project: str) -> threading.RLock:
        """One lock per project: runs that modify papers.json are serialized."""
        with _locks_guard:
            return _locks[str(self.project_path(project).resolve())]

    def get_meta(self, project: str) -> dict:
        p = self.meta_path(project)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"context": ""}

    def set_meta(self, project: str, **fields) -> dict:
        meta = {**self.get_meta(project), **fields}
        _write_json(self.meta_path(project), meta)
        return meta

    # ── papers ───────────────────────────────────────────────────────────────
    def get_papers(self, project: str) -> list[dict]:
        p = self.papers_db_path(project)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []

    def save_papers(self, project: str, papers: list[dict]) -> None:
        _write_json(self.papers_db_path(project), papers)

    # ── sessions (PRISMA trail) ──────────────────────────────────────────────
    def new_session(self, project: str, kind: str) -> tuple[str, Path]:
        session_id = f"{datetime.now():%Y%m%d_%H%M%S}_{kind}_{uuid.uuid4().hex[:4]}"
        path = self.sessions_dir(project) / session_id
        (path / "results").mkdir(parents=True, exist_ok=True)
        return session_id, path

    def save_raw_results(self, session_path: Path, source: str, records: list[dict]) -> None:
        _write_json(session_path / "results" / f"{source}.json", records)

    def save_session(self, session_path: Path, data: dict) -> None:
        _write_json(session_path / "session.json", data)

    def list_sessions(self, project: str) -> list[dict]:
        d = self.sessions_dir(project)
        if not d.exists():
            return []
        out = []
        for s in sorted(d.iterdir(), reverse=True):
            f = s / "session.json"
            if f.exists():
                out.append(json.loads(f.read_text(encoding="utf-8")))
        return out
