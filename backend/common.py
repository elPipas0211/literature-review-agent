"""Shared helpers for the routers: project lookup and Server-Sent Events."""
import asyncio
import json
import threading
from typing import Callable

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from backend.config import get_config
from src.pipeline import JobCancelled
from src.storage.project_manager import InvalidProjectName, ProjectManager, validate_name


def get_pm() -> ProjectManager:
    return ProjectManager(get_config()["storage"]["projects_dir"])


def check_name(name: str) -> str:
    try:
        return validate_name(name)
    except InvalidProjectName as exc:
        raise HTTPException(422, str(exc))


def require_project(project: str) -> ProjectManager:
    check_name(project)
    pm = get_pm()
    if not pm.exists(project):
        raise HTTPException(404, f"Project '{project}' not found")
    return pm


def sse_job(job: Callable[[Callable[[dict], None]], dict | None]) -> StreamingResponse:
    """
    Run `job(emit)` in a thread and stream its events; the return value is sent as type=result.
    If the browser disconnects (the user pressed Cancel), the next emit() raises
    JobCancelled inside the job, which stops it before anything is saved.
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    cancelled = threading.Event()

    def send(event: dict):
        loop.call_soon_threadsafe(queue.put_nowait, event)

    def emit(event: dict):
        if cancelled.is_set():
            raise JobCancelled()
        send(event)

    def worker():
        try:
            result = job(emit)
            send({"type": "result", "result": result})
        except JobCancelled:
            pass  # nobody is listening any more
        except Exception as exc:  # surfaced to the UI instead of a silent 500
            send({"type": "error", "message": str(exc)})
        finally:
            send({"type": "_eof"})

    threading.Thread(target=worker, daemon=True).start()

    async def stream():
        finished = False
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=2.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if event.get("type") == "_eof":
                    finished = True
                    break
                yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
        finally:
            if not finished:  # client went away mid-run
                cancelled.set()

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
