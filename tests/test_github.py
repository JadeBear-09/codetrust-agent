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
            "state": "CLOSED",
            "closedAt": "2026-07-05T19:08:24Z",
            "mergedAt": None,
            "author": {"login": "contributor"},
            "comments": [
                {
                    "author": {"login": "maintainer"},
                    "authorAssociation": "MEMBER",
                    "body": "Out of scope.",
                    "url": "https://github.com/acme/payments/pull/7#issuecomment-1",
                    "createdAt": "2026-07-05T19:08:24Z",
                }
            ],
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
    assert change.state == "CLOSED"
    assert change.merged_at is None
    assert change.author == "contributor"
    assert change.comments[0].association == "MEMBER"
    assert change.comments[0].body == "Out of scope."


def test_rejects_ambiguous_reference() -> None:
    with pytest.raises(ValueError, match="OWNER/REPO#NUMBER"):
        github.load_pull_request("7")


def test_accepts_github_pull_request_url(monkeypatch: pytest.MonkeyPatch) -> None:
    metadata = json.dumps(
        {
            "title": "Change",
            "body": "Body",
            "url": "https://github.com/acme/payments/pull/7",
            "baseRefOid": "base",
            "headRefOid": "head",
        }
    )
    monkeypatch.setattr(
        github,
        "_run_gh",
        lambda arguments: metadata if "view" in arguments else "diff --git a/a b/a\n",
    )

    change = github.load_pull_request("https://github.com/acme/payments/pull/7")

    assert change.repo == "acme/payments"
    assert change.number == 7
