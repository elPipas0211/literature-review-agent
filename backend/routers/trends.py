from fastapi import APIRouter, HTTPException, Query

from backend.config import get_config
from src.pipeline import global_trend

router = APIRouter(prefix="/api", tags=["trends"])


@router.get("/trend")
def trend(q: str = Query(min_length=2), year_from: int | None = 2000, year_to: int | None = None):
    """Works per year in all of OpenAlex for a topic (to judge whether it is growing)."""
    try:
        return global_trend(q, get_config(), year_from, year_to)
    except Exception as exc:
        raise HTTPException(502, f"OpenAlex error: {exc}")
