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
            "author": {"login": "contributor"},
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
    assert change.author == "contributor"


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


def test_loads_general_docs_and_structure_from_exact_base(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    tree = json.dumps(
        {
            "truncated": False,
            "tree": [
                {"path": "README.md", "type": "blob", "size": 40},
                {"path": "CONTRIBUTING.md", "type": "blob", "size": 50},
                {"path": "docs/ARCHITECTURE.md", "type": "blob", "size": 60},
                {"path": "src/payments/retry.py", "type": "blob", "size": 70},
                {"path": "src/payments/client.py", "type": "blob", "size": 80},
                {"path": "vendor/tool/README.md", "type": "blob", "size": 30},
            ],
        }
    )

    def fake_run(arguments: list[str]) -> str:
        calls.append(arguments)
        if "/git/trees/" in arguments[3]:
            return tree
        if arguments[3] == "repos/acme/payments":
            return json.dumps(
                {
                    "description": "Payment service",
                    "language": "Python",
                    "topics": ["payments", "retries"],
                    "created_at": "2020-01-01T00:00:00Z",
                    "default_branch": "main",
                }
            )
        if arguments[3] == "repos/acme/payments/commits":
            return json.dumps(
                [
                    {
                        "sha": "abc123",
                        "commit": {
                            "message": "Preserve retry safety\n\nDetails",
                            "author": {"date": "2026-01-01T00:00:00Z"},
                        },
                    }
                ]
            )
        path = arguments[3].split("/contents/", 1)[1]
        return f"Base document: {path}"

    monkeypatch.setattr(github, "_run_gh", fake_run)

    context = github.load_repository_context(
        "acme/payments",
        "abcdef1234567",
        ("src/payments/retry.py",),
    )

    assert [item.path for item in context.documents] == [
        "README.md",
        "CONTRIBUTING.md",
        "docs/ARCHITECTURE.md",
    ]
    assert context.structure[0] == "src/payments/retry.py"
    assert "src/payments/client.py" in context.structure
    assert [item.path for item in context.source_files] == [
        "src/payments/retry.py",
        "src/payments/client.py",
    ]
    content_calls = [call for call in calls if "/contents/" in call[3]]
    assert all("ref=abcdef1234567" in call for call in content_calls)
    assert context.metadata is not None
    assert context.metadata.description == "Payment service"
    assert context.history[0].title == "Preserve retry safety"
    assert len(context.sha256) == 64


def test_repository_context_skips_unreadable_files_and_keeps_other_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tree = json.dumps(
        {
            "tree": [
                {"path": "README.md", "type": "blob", "size": 20},
                {"path": "src/service.py", "type": "blob", "size": 20},
                {"path": "tests/test_service.py", "type": "blob", "size": 20},
                {"path": "pyproject.toml", "type": "blob", "size": 20},
            ]
        }
    )

    def fake_run(arguments: list[str]) -> str:
        endpoint = arguments[3]
        if "/git/trees/" in endpoint:
            return tree
        if endpoint.endswith("/contents/README.md"):
            raise RuntimeError("file unavailable")
        if "/contents/" in endpoint:
            return f"base content for {endpoint}"
        raise RuntimeError("optional metadata unavailable")

    monkeypatch.setattr(github, "_run_gh", fake_run)

    context = github.load_repository_context(
        "acme/service",
        "abcdef1234567",
        ("src/service.py",),
    )

    assert context.documents == ()
    assert [item.path for item in context.source_files] == [
        "src/service.py",
        "tests/test_service.py",
        "pyproject.toml",
    ]
    assert context.metadata is None
    assert context.history == ()
