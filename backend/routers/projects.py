import shutil
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.common import check_name, get_pm, require_project
from backend.config import get_config
from src.pipeline import rescore_library

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("")
def list_projects():
    return get_pm().list_projects()


@router.get("/summary")
def project_summaries():
    """One card per project for the start page, most recently changed first."""
    pm = get_pm()
    out = []
    for name in pm.list_projects():
        papers = pm.get_papers(name)
        db = pm.papers_db_path(name)
        sessions = pm.sessions_dir(name)
        out.append({
            "name": name,
            "context": pm.get_meta(name).get("context", ""),
            "papers": len(papers),
            "relevant": sum(1 for p in papers if (p.get("evaluation") or {}).get("category") == "relevante"),
            "starred": sum(1 for p in papers if p.get("starred")),
            "searches": sum(1 for d in sessions.iterdir() if d.is_dir()) if sessions.exists() else 0,
            "updated_at": datetime.fromtimestamp(db.stat().st_mtime).isoformat(timespec="minutes"),
        })
    return sorted(out, key=lambda x: x["updated_at"], reverse=True)


class CreateRequest(BaseModel):
    name: str
    context: str = ""


@router.post("", status_code=201)
def create_project(req: CreateRequest):
    name = check_name(req.name)
    pm = get_pm()
    if pm.project_path(name).exists():
        raise HTTPException(409, f"Project '{name}' already exists")
    pm.init_project(name)
    if req.context.strip():
        pm.set_meta(name, context=req.context.strip())
    return {"name": name}


class RenameRequest(BaseModel):
    new_name: str


@router.patch("/{name}")
def rename_project(name: str, req: RenameRequest):
    pm = require_project(name)
    new_name = check_name(req.new_name)
    if pm.project_path(new_name).exists():
        raise HTTPException(409, f"Project '{new_name}' already exists")
    with pm.lock(name):
        pm.project_path(name).rename(pm.project_path(new_name))
    return {"name": new_name}


@router.delete("/{name}")
def delete_project(name: str):
    pm = require_project(name)
    with pm.lock(name):
        shutil.rmtree(pm.project_path(name))
    return {"deleted": name}


@router.get("/{name}/meta")
def get_meta(name: str):
    return require_project(name).get_meta(name)


class ContextRequest(BaseModel):
    context: str


@router.put("/{name}/context")
def set_context(name: str, req: ContextRequest):
    """Change the research context and rescore the whole library against it."""
    require_project(name)
    return rescore_library(name, req.context, get_config())
