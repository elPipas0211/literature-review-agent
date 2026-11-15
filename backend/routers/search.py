from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.common import check_name, get_pm, sse_job
from backend.config import get_config
from src.pipeline import run_search

router = APIRouter(prefix="/api/projects", tags=["search"])


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    context: str | None = None
    max_results: int = Field(100, ge=1, le=1000)  # per source
    year_from: int | None = None
    year_to: int | None = None


@router.post("/{project}/search")
async def search(project: str, req: SearchRequest):
    check_name(project)
    get_pm().init_project(project)
    return sse_job(lambda emit: run_search(
        project, req.query, req.context, req.max_results, get_config(), emit,
        year_from=req.year_from, year_to=req.year_to,
    ))
