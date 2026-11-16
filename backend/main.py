import logging
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_config
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
    return {"evaluation": cfg["evaluation"], "embeddings": {"model": cfg["embeddings"]["model"]}}


for r in (projects, papers, search, import_csv, query, clusters, trends):
    app.include_router(r.router)
