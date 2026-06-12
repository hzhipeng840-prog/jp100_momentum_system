from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
VERSION_PATH = PROJECT_ROOT / "VERSION"


def current_version() -> str:
    try:
        version = VERSION_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return "v0"
    return version or "v0"
