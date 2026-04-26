from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import get_config
from src.embeddings.chroma_store import MasterVectorDB
from src.storage.project_manager import ProjectManager

router = APIRouter(prefix="/api/projects", tags=["query"])


class QueryRequest(BaseModel):
    question: str
    top: int = 5


@router.post("/{project}/query")
def semantic_query(project: str, req: QueryRequest):
    config = get_config()
    pm = ProjectManager(config["storage"]["projects_dir"])
    chroma_dir = pm.chroma_dir(project)
    if not chroma_dir.exists():
        raise HTTPException(404, f"No ChromaDB for project '{project}'")
    db = MasterVectorDB(persist_dir=chroma_dir, model_name=config["embeddings"]["model"])
    if db.count() == 0:
        return []
    return db.query(req.question, n_results=req.top)
