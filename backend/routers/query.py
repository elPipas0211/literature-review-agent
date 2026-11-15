from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.common import require_project
from backend.config import get_config
from src.pipeline import semantic_query

router = APIRouter(prefix="/api/projects", tags=["query"])


class QueryRequest(BaseModel):
    question: str = Field(min_length=1)
    top: int = Field(10, ge=1, le=100)


@router.post("/{project}/query")
def query(project: str, req: QueryRequest):
    require_project(project)
    return semantic_query(project, req.question, req.top, get_config())
