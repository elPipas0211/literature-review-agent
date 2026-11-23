from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.common import require_project, sse_job
from backend.config import get_config
from src.pipeline import (annotate, complete_citation_details, draw_validation_sample, prisma_summary,
                          run_snowball)
from src.utils.bibtex_exporter import export_bibtex, library_bibtex
from src.utils.apa import apa_html, apa_in_text, apa_text, reference_list_rtf
from src.utils.exporters import to_csv, to_ris

router = APIRouter(prefix="/api/projects", tags=["papers"])


@router.get("/{project}/papers")
def get_papers(project: str):
    pm = require_project(project)
    papers = pm.get_papers(project)
    bib = library_bibtex(papers)
    for p in papers:
        p["cite_key"], p["bibtex"] = bib[p["id"]]
        p["apa"] = {"text": apa_text(p), "html": apa_html(p), "in_text": apa_in_text(p)}
    return papers


@router.get("/{project}/prisma")
def get_prisma(project: str):
    require_project(project)
    return prisma_summary(project, get_config())


class ExportRequest(BaseModel):
    format: Literal["csv", "ris", "bib", "apa"]
    ids: list[str] | None = None  # None = whole library


_MEDIA = {"csv": "text/csv; charset=utf-8", "ris": "application/x-research-info-systems",
          "bib": "application/x-bibtex", "apa": "application/rtf"}


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
        if req.format == "apa":
            body = reference_list_rtf(papers)  # alphabetical, as APA requires
        else:
            body = to_csv(papers) if req.format == "csv" else to_ris(papers)
    ext = "rtf" if req.format == "apa" else req.format
    suffix = "_APA_references" if req.format == "apa" else ""
    filename = f"{project}{suffix}_{datetime.now():%Y%m%d}.{ext}"
    return Response(body, media_type=_MEDIA[req.format],
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


class AnnotateRequest(BaseModel):
    id: str
    starred: bool | None = None
    note: str | None = None
    validation: Literal["relevant", "irrelevant", "unsure", ""] | None = None  # "" clears


@router.post("/{project}/annotate")
def annotate_paper(project: str, req: AnnotateRequest):
    """Star a paper and/or save a note (reading list)."""
    require_project(project)
    try:
        return annotate(project, req.id, get_config(), req.starred, req.note, req.validation)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


class SnowballRequest(BaseModel):
    id: str
    direction: Literal["references", "citations", "both"] = "both"
    max_results: int = Field(100, ge=1, le=1000)


@router.post("/{project}/snowball")
async def snowball(project: str, req: SnowballRequest):
    """Citation searching: add a paper's references and/or the papers that cite it."""
    require_project(project)
    return sse_job(lambda emit: run_snowball(project, req.id, req.direction, req.max_results,
                                             get_config(), emit))


class SampleRequest(BaseModel):
    size: int = Field(50, ge=1, le=500)


@router.post("/{project}/validation/sample")
def validation_sample(project: str, req: SampleRequest):
    """Grow the random sample used to check how well the score ranks papers."""
    require_project(project)
    return draw_validation_sample(project, req.size, get_config())


@router.post("/{project}/complete-details")
async def complete_details(project: str):
    """Fill missing volume / issue / pages from OpenAlex (streams progress)."""
    require_project(project)
    return sse_job(lambda emit: complete_citation_details(project, get_config(), emit))
