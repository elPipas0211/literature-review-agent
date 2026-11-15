"""Shared bits for the CLI scripts: config loading and event printing."""
import json
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.config import get_config  # noqa: E402  (resolves projects_dir to an absolute path)


def print_event(event: dict) -> None:
    kind = event.pop("type", "?")
    print(f"[{kind}] " + ", ".join(f"{k}={v}" for k, v in event.items()), flush=True)


def dump(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


__all__ = ["get_config", "print_event", "dump"]
