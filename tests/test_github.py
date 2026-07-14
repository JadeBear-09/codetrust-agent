import json

import pytest

import codetrust.github as github


def test_loads_pull_request(monkeypatch: pytest.MonkeyPatch) -> None:
    metadata = json.dumps(
        {
            "title": "Safe retries",
            "body": "Never duplicate payment.",
            "url": "https://github.com/acme/payments/pull/7",
            "baseRefOid": "base-sha",
            "headRefOid": "head-sha",
        }
    )

    def fake_run(arguments: list[str]) -> str:
        return metadata if "view" in arguments else "diff --git a/a.py b/a.py\n"

    monkeypatch.setattr(github, "_run_gh", fake_run)

    change = github.load_pull_request("acme/payments#7")

    assert change.number == 7
    assert change.repo == "acme/payments"
    assert "Safe retries" in change.ticket
    assert change.head_sha == "head-sha"


def test_rejects_ambiguous_reference() -> None:
    with pytest.raises(ValueError, match="OWNER/REPO#NUMBER"):
        github.load_pull_request("7")
