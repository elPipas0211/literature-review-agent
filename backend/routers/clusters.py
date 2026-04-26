import asyncio
import json
import threading

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.config import get_config
from src.storage.project_manager import ProjectManager

router = APIRouter(prefix="/api/projects", tags=["clusters"])


@router.get("/{project}/clusters")
def get_clusters(project: str):
    config = get_config()
    pm = ProjectManager(config["storage"]["projects_dir"])
    clusters_path = pm.master_db_path(project) / "clusters.json"
    if not clusters_path.exists():
        return {"clusters": [], "num_clusters": 0, "generated": False}
    data = json.loads(clusters_path.read_text(encoding="utf-8"))
    data["generated"] = True
    return data


class ClusterRequest(BaseModel):
    k_min: int = 2
    k_max: int = 8
    top_kw: int = 5


@router.post("/{project}/clusters")
async def generate_clusters(project: str, req: ClusterRequest):
    config = get_config()
    pm = ProjectManager(config["storage"]["projects_dir"])
    chroma_dir = pm.chroma_dir(project)
    if not chroma_dir.exists():
        raise HTTPException(404, f"No ChromaDB for project '{project}'")

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def cluster_thread():
        import numpy as np
        import chromadb
        from sklearn.cluster import KMeans
        from keybert import KeyBERT
        from sentence_transformers import SentenceTransformer
        from datetime import datetime

        def emit(event):
            loop.call_soon_threadsafe(queue.put_nowait, event)

        def _find_elbow(inertias: list) -> int:
            """0-based index of the elbow using max perpendicular distance."""
            if len(inertias) <= 1:
                return 0
            n = len(inertias)
            xs = np.linspace(0.0, 1.0, n)
            y_lo, y_hi = min(inertias), max(inertias)
            span = max(y_hi - y_lo, 1e-12)
            ys = np.array([(v - y_lo) / span for v in inertias])
            x1, y1 = xs[0], ys[0]
            x2, y2 = xs[-1], ys[-1]
            dx, dy = x2 - x1, y2 - y1
            denom = (dx**2 + dy**2) ** 0.5 + 1e-12
            dists = [abs(dy * (x1 - x) - dx * (y1 - y)) / denom
                     for x, y in zip(xs, ys)]
            return int(np.argmax(dists))

        try:
            client = chromadb.PersistentClient(path=str(chroma_dir))
            col = client.get_or_create_collection(
                "papers", metadata={"hnsw:space": "cosine"}
            )
            if col.count() == 0:
                emit({"type": "error", "message": "ChromaDB is empty"})
                return

            result = col.get(include=["embeddings", "metadatas"])
            embeddings = result["embeddings"]
            metadatas = result["metadatas"]
            n = len(embeddings)
            emit({"type": "loaded", "count": n})

            X = np.array(embeddings, dtype=np.float32)
            k_min = max(2, req.k_min)
            k_max = min(req.k_max, n)
            if k_min > k_max:
                k_min = k_max

            # ── Elbow method: try k_min … k_max ───────────────────────────
            emit({"type": "elbow_start", "k_min": k_min, "k_max": k_max})
            ks = list(range(k_min, k_max + 1))
            inertias: list[float] = []
            models: list = []
            for k in ks:
                km = KMeans(n_clusters=k, random_state=42, n_init=10)
                km.fit(X)
                inertias.append(float(km.inertia_))
                models.append(km)
                emit({"type": "elbow_step", "k": k, "inertia": round(float(km.inertia_), 2)})

            best_idx = _find_elbow(inertias)
            best_k = ks[best_idx]
            labels = models[best_idx].labels_
            emit({"type": "clustered", "k": best_k, "num_clusters": best_k})

            model_name = config["embeddings"]["model"]
            emit({"type": "labeling"})
            kw_model = KeyBERT(model=SentenceTransformer(model_name))

            clusters_out = []
            for cid in range(best_k):
                idxs = [i for i, lbl in enumerate(labels) if lbl == cid]
                metas = [metadatas[i] for i in idxs]
                combined = " ".join(
                    f"{m.get('title', '')} {m.get('abstract', '')}" for m in metas
                )[:8000]
                kws = kw_model.extract_keywords(
                    combined, keyphrase_ngram_range=(1, 3),
                    stop_words="english", use_mmr=True,
                    diversity=0.5, top_n=req.top_kw,
                )
                keyphrases = [kw for kw, _ in kws]
                label = " | ".join(keyphrases[:3]) if keyphrases else f"Cluster {cid}"
                papers_out = sorted(
                    [{"title": m.get("title", ""), "year": m.get("year"),
                      "doi": m.get("doi", ""), "citationCount": m.get("citationCount"),
                      "venue": m.get("venue", ""), "category": m.get("category", "")}
                     for m in metas],
                    key=lambda p: p.get("citationCount") or 0, reverse=True,
                )
                clusters_out.append({
                    "id": cid, "label": label, "keyphrases": keyphrases,
                    "paper_count": len(papers_out), "papers": papers_out,
                })

            clusters_out.sort(key=lambda c: c["paper_count"], reverse=True)

            output = {
                "project": project,
                "generated_at": datetime.now().isoformat(),
                "total_papers": n,
                "num_clusters": best_k,
                "noise_papers": 0,
                "kmeans_params": {"k": best_k, "k_min": k_min, "k_max": k_max},
                "inertia_curve": list(zip(ks, [round(v, 2) for v in inertias])),
                "clusters": clusters_out,
                "noise": [],
            }
            out_path = pm.master_db_path(project) / "clusters.json"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            emit({"type": "done", "num_clusters": best_k, "k": best_k})

        except Exception as exc:
            emit({"type": "error", "message": str(exc)})
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "_eof"})

    threading.Thread(target=cluster_thread, daemon=True).start()

    async def generate():
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=2.0)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue
            if event.get("type") == "_eof":
                break
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
