import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile

from backend.common import require_project, sse_job
from backend.config import get_config
from src.pipeline import run_import

router = APIRouter(prefix="/api/projects", tags=["import"])


@router.post("/{project}/import")
async def import_csv(project: str, file: UploadFile = File(...), context: str | None = Form(None)):
    require_project(project)
    suffix = Path(file.filename or "upload.csv").suffix or ".csv"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    def job(emit):
        try:
            return run_import(project, tmp_path, context, get_config(), emit, filename=file.filename)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    return sse_job(job)
