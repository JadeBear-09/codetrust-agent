from __future__ import annotations

import json
import os
import threading
from pathlib import Path

_LOCK = threading.Lock()
_MAX_RUNS = 100


def save_run(report: dict) -> None:
    """Persist bounded report history without storing ticket or diff contents."""
    with _LOCK:
        runs = _read_runs()
        runs = [item for item in runs if item.get("run_id") != report.get("run_id")]
        runs.insert(0, report)
        _write_runs(runs[:_MAX_RUNS])


def list_runs(limit: int = 20) -> list[dict]:
    with _LOCK:
        return _read_runs()[:limit]


def get_run(run_id: str) -> dict:
    with _LOCK:
        run = next((item for item in _read_runs() if item.get("run_id") == run_id), None)
        if run is None:
            raise KeyError("Verification run not found")
        return run


def _data_path() -> Path:
    configured = os.getenv("CODETRUST_DATA_DIR")
    root = Path(configured) if configured else Path.cwd() / ".codetrust"
    return root / "runs.json"


def _read_runs() -> list[dict]:
    path = _data_path()
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return data if isinstance(data, list) else []


def _write_runs(runs: list[dict]) -> None:
    path = _data_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(runs, indent=2) + "\n")
    temporary.replace(path)
