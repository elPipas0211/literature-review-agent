import asyncio
import json
import threading

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.config import get_config
from backend.pipeline import run_search

router = APIRouter(prefix="/api/projects", tags=["search"])


class SearchRequest(BaseModel):
    query: str
    context: str | None = None
    max_results: int = 50


@router.post("/{project}/search")
async def search(project: str, req: SearchRequest):
    config = get_config()
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    done = threading.Event()

    def pipeline_thread():
        def emit(event: dict):
            loop.call_soon_threadsafe(queue.put_nowait, event)
        try:
            run_search(project, req.query, req.context, req.max_results, config, emit)
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "error", "message": str(exc)})
        finally:
            done.set()
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "_eof"})

    threading.Thread(target=pipeline_thread, daemon=True).start()

    async def generate():
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=1.0)
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
