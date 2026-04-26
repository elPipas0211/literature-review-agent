import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import ROOT, get_config
from src.storage.project_manager import ProjectManager

router = APIRouter(prefix="/api/projects", tags=["projects"])

# Reject filesystem-unsafe characters; allow letters, digits, spaces, hyphens,
# underscores, dots. Must be 1–50 chars and not start/end with whitespace.
_UNSAFE = re.compile(r'[\\/:*?"<>|]')


def _validate(name: str) -> str:
    name = name.strip()
    if not name:
        raise HTTPException(422, "Project name cannot be empty")
    if len(name) > 50:
        raise HTTPException(422, "Project name must be 50 characters or fewer")
    if _UNSAFE.search(name):
        raise HTTPException(422, "Project name contains invalid characters: \\ / : * ? \" < > |")
    return name


def _pm() -> ProjectManager:
    return ProjectManager(get_config()["storage"]["projects_dir"])


def _projects_dir() -> Path:
    return ROOT / get_config()["storage"]["projects_dir"]


@router.get("")
def list_projects():
    d = _projects_dir()
    if not d.exists():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_dir() and (p / "master_db").exists())


class CreateRequest(BaseModel):
    name: str


@router.post("", status_code=201)
def create_project(req: CreateRequest):
    name = _validate(req.name)
    pm = _pm()
    if pm.project_path(name).exists():
        raise HTTPException(409, f"Project '{name}' already exists")
    pm.init_project(name)
    return {"name": name}


class RenameRequest(BaseModel):
    new_name: str


@router.patch("/{name}")
def rename_project(name: str, req: RenameRequest):
    new_name = _validate(req.new_name)
    pm = _pm()
    old_path = pm.project_path(name)
    if not old_path.exists():
        raise HTTPException(404, f"Project '{name}' not found")
    new_path = pm.project_path(new_name)
    if new_path.exists():
        raise HTTPException(409, f"Project '{new_name}' already exists")
    old_path.rename(new_path)
    return {"name": new_name}


@router.delete("/{name}", status_code=200)
def delete_project(name: str):
    import shutil
    pm = _pm()
    path = pm.project_path(name)
    if not path.exists():
        raise HTTPException(404, f"Project '{name}' not found")
    shutil.rmtree(path)
    return {"deleted": name}
