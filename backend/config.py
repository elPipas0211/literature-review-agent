"""
Configuration: config.yaml (committed defaults) + .env (local secrets, git-ignored).

The OpenAlex API key is a secret, so it never goes in config.yaml: it is read
from the OPENALEX_API_KEY environment variable, which .env can provide.
"""
import os
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
_config: dict | None = None


def _load_env_file() -> None:
    """Minimal KEY=VALUE reader; real environment variables win."""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$", line)
        if m and not line.lstrip().startswith("#"):
            os.environ.setdefault(m.group(1), m.group(2).strip("'\""))


def get_config() -> dict:
    global _config
    if _config is None:
        _load_env_file()
        raw = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
        # Resolve projects_dir to an absolute path so pipeline code never depends
        # on the process cwd (which changes when uvicorn is started from a sub-dir).
        raw["storage"]["projects_dir"] = str(ROOT / raw["storage"]["projects_dir"])
        oa = raw.setdefault("sources", {}).setdefault("openalex", {}) or {}
        raw["sources"]["openalex"] = oa
        oa["api_key"] = os.environ.get("OPENALEX_API_KEY", "").strip() or None
        oa["email"] = os.environ.get("OPENALEX_EMAIL", "").strip() or oa.get("email") or None
        _config = raw
    return _config


def save_openalex_settings(api_key: str | None = None, email: str | None = None) -> None:
    """Write the key/email to .env (creating or updating the lines) and reload the config."""
    global _config
    updates = {}
    if api_key is not None:
        updates["OPENALEX_API_KEY"] = api_key.strip()
    if email is not None:
        updates["OPENALEX_EMAIL"] = email.strip()
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    out, seen = [], set()
    for line in lines:
        m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if m and m.group(1) in updates:
            seen.add(m.group(1))
            if updates[m.group(1)]:
                out.append(f"{m.group(1)}={updates[m.group(1)]}")
            continue  # empty value = remove the line
        out.append(line)
    out += [f"{k}={v}" for k, v in updates.items() if k not in seen and v]
    ENV_FILE.write_text("\n".join(out) + ("\n" if out else ""), encoding="utf-8")
    for k, v in updates.items():  # the new value must win over the old process environment
        if v:
            os.environ[k] = v
        else:
            os.environ.pop(k, None)
    _config = None
