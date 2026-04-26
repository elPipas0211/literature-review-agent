import asyncio
import json
import shutil
import tempfile
import threading
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.config import get_config
from backend.pipeline import run_import

router = APIRouter(prefix="/api/projects", tags=["import"])


@router.post("/{project}/import")
async def import_csv(
    project: str,
    file: UploadFile = File(...),
    context: str | None = Form(None),
):
    config = get_config()

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def pipeline_thread():
        def emit(event: dict):
            loop.call_soon_threadsafe(queue.put_nowait, event)
        try:
            result = run_import(project, tmp_path, context, config, emit)
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "result", **result})
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "error", "message": str(exc)})
        finally:
            Path(tmp_path).unlink(missing_ok=True)
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "_eof"})

    threading.Thread(target=pipeline_thread, daemon=True).start()

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
