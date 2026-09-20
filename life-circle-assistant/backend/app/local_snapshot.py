import json
from pathlib import Path
from typing import Any


SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "data" / "baidu_snapshot.json"


def load_snapshot() -> dict[str, Any] | None:
    if not SNAPSHOT_PATH.exists():
        return None
    try:
        with SNAPSHOT_PATH.open("r", encoding="utf-8") as file:
            snapshot = json.load(file)
    except (OSError, json.JSONDecodeError):
        return None
    return snapshot if isinstance(snapshot, dict) else None


def snapshot_path() -> str:
    return str(SNAPSHOT_PATH)
