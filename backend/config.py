import yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_config: dict | None = None


def get_config() -> dict:
    global _config
    if _config is None:
        raw = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
        # Resolve projects_dir to an absolute path so pipeline code never depends
        # on the process cwd (which changes when uvicorn is started from a sub-dir).
        raw["storage"]["projects_dir"] = str(ROOT / raw["storage"]["projects_dir"])
        _config = raw
    return _config
