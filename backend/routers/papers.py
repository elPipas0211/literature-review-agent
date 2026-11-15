from datetime import datetime
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel

from backend.common import require_project
from backend.config import get_config
from src.pipeline import prisma_summary
from src.utils.bibtex_exporter import export_bibtex, library_bibtex
from src.utils.exporters import to_csv, to_ris

router = APIRouter(prefix="/api/projects", tags=["papers"])


@router.get("/{project}/papers")
def get_papers(project: str):
    pm = require_project(project)
    papers = pm.get_papers(project)
    bib = library_bibtex(papers)
    for p in papers:
        p["cite_key"], p["bibtex"] = bib[p["id"]]
    return papers


@router.get("/{project}/prisma")
def get_prisma(project: str):
    require_project(project)
    return prisma_summary(project, get_config())


class ExportRequest(BaseModel):
    format: Literal["csv", "ris", "bib"]
    ids: list[str] | None = None  # None = whole library


_MEDIA = {"csv": "text/csv; charset=utf-8", "ris": "application/x-research-info-systems",
          "bib": "application/x-bibtex"}


@router.post("/{project}/export")
def export(project: str, req: ExportRequest):
    pm = require_project(project)
    library = pm.get_papers(project)
    wanted = set(req.ids) if req.ids is not None else None
    if req.format == "bib":
        body = export_bibtex(library, only_ids=wanted)  # keys computed over the whole library
    else:
        order = {pid: i for i, pid in enumerate(req.ids or [])}
        papers = [p for p in library if wanted is None or p["id"] in wanted]
        if req.ids:
            papers.sort(key=lambda p: order.get(p["id"], 0))
        body = to_csv(papers) if req.format == "csv" else to_ris(papers)
    filename = f"{project}_{datetime.now():%Y%m%d}.{req.format}"
    return Response(body, media_type=_MEDIA[req.format],
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
