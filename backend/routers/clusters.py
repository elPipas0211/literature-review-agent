import json

from fastapi import APIRouter
from pydantic import BaseModel

from backend.common import require_project, sse_job
from backend.config import get_config
from src.clustering import run_clustering

router = APIRouter(prefix="/api/projects", tags=["clusters"])


@router.get("/{project}/clusters")
def get_clusters(project: str):
    pm = require_project(project)
    path = pm.clusters_path(project)
    if not path.exists():
        return {"clusters": [], "num_clusters": 0, "generated": False}
    return {**json.loads(path.read_text(encoding="utf-8")), "generated": True}


class ClusterRequest(BaseModel):
    k_min: int = 2
    k_max: int = 8
    top_kw: int = 5
    only_categories: list[str] | None = None


@router.post("/{project}/clusters")
async def generate_clusters(project: str, req: ClusterRequest):
    require_project(project)
    return sse_job(lambda emit: {"num_clusters": run_clustering(
        project, get_config(), emit, req.k_min, req.k_max, req.top_kw, req.only_categories,
    )["num_clusters"]})
