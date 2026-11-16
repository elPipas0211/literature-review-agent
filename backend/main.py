import logging
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_config, save_openalex_settings
from backend.routers import clusters, import_csv, papers, projects, query, search, trends
from src.embeddings.model import get_embedder

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Load the embedding model once, in the background, so the first search is fast.
    threading.Thread(target=lambda: get_embedder(get_config()), daemon=True).start()
    yield


app = FastAPI(title="Literature Review Agent", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/config")
def public_config():
    """Defaults the frontend needs (scoring formula), read from config.yaml."""
    cfg = get_config()
    oa = cfg["sources"]["openalex"]
    return {
        "evaluation": cfg["evaluation"],
        "embeddings": {"model": cfg["embeddings"]["model"]},
        # Never send the key itself to the browser, only whether one is set.
        "openalex": {"has_key": bool(oa.get("api_key")), "email": oa.get("email") or ""},
    }


class OpenAlexSettings(BaseModel):
    api_key: str | None = Field(None, max_length=200)  # None = keep, "" = remove
    email: str | None = Field(None, max_length=200)


@app.put("/api/settings/openalex")
def set_openalex(req: OpenAlexSettings):
    """Save the OpenAlex API key / email to the local .env file (git-ignored)."""
    save_openalex_settings(req.api_key, req.email)
    return public_config()["openalex"]


for r in (projects, papers, search, import_csv, query, clusters, trends):
    app.include_router(r.router)
