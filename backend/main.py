import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import clusters, import_csv, papers, projects, query, search

app = FastAPI(title="Literature Review Agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(papers.router)
app.include_router(search.router)
app.include_router(import_csv.router)
app.include_router(query.router)
app.include_router(clusters.router)
