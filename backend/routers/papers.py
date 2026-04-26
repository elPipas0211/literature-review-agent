from fastapi import APIRouter, HTTPException
from backend.config import get_config
from src.storage.project_manager import ProjectManager

router = APIRouter(prefix="/api/projects", tags=["papers"])


@router.get("/{project}/papers")
def get_papers(project: str):
    config = get_config()
    pm = ProjectManager(config["storage"]["projects_dir"])
    path = pm.papers_db_path(project)
    if not path.exists():
        raise HTTPException(404, f"Project '{project}' not found")
    import json
    papers = json.loads(path.read_text(encoding="utf-8"))
    # Ensure every paper has a stable id field for the frontend
    for p in papers:
        doi = ((p.get("externalIds") or {}).get("DOI") or "").strip().lower()
        p["_id"] = doi or p.get("title", "")[:40]
    return papers


@router.get("/{project}/stats")
def get_stats(project: str):
    config = get_config()
    pm = ProjectManager(config["storage"]["projects_dir"])
    path = pm.papers_db_path(project)
    if not path.exists():
        raise HTTPException(404, f"Project '{project}' not found")
    import json
    papers = json.loads(path.read_text(encoding="utf-8"))
    cats: dict[str, int] = {}
    for p in papers:
        cat = (p.get("evaluation") or {}).get("category", "unevaluated")
        cats[cat] = cats.get(cat, 0) + 1
    return {"total": len(papers), "by_category": cats}
