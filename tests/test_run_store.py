from __future__ import annotations

import json

import pytest

from codetrust.run_store import get_run, list_runs, save_run


def test_run_store_persists_latest_first(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CODETRUST_DATA_DIR", str(tmp_path))
    save_run({"run_id": "ct-one", "verdict": "PASS"})
    save_run({"run_id": "ct-two", "verdict": "BLOCK"})

    assert [item["run_id"] for item in list_runs()] == ["ct-two", "ct-one"]
    assert get_run("ct-one")["verdict"] == "PASS"
    assert json.loads((tmp_path / "runs.json").read_text())[0]["run_id"] == "ct-two"


def test_run_store_replaces_duplicate_and_limits_results(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CODETRUST_DATA_DIR", str(tmp_path))
    save_run({"run_id": "ct-one", "risk_score": 10})
    save_run({"run_id": "ct-one", "risk_score": 20})

    assert list_runs(1) == [{"run_id": "ct-one", "risk_score": 20}]


def test_run_store_missing_run(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CODETRUST_DATA_DIR", str(tmp_path))
    with pytest.raises(KeyError, match="Verification run not found"):
        get_run("ct-missing")
