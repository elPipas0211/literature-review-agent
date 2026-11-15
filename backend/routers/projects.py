import shutil

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.common import check_name, get_pm, require_project
from backend.config import get_config
from src.pipeline import rescore_library

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("")
def list_projects():
    return get_pm().list_projects()


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
