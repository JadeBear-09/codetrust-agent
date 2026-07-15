import hashlib
import json
from pathlib import Path

from codetrust.agent import verify_change
from codetrust.models import InterpretationClaim, ScopeComparison, Verdict
from codetrust.report import render_html, render_markdown, write_reports
from codetrust.rules import risk_score


def test_offline_agent_blocks_risky_demo(tmp_path: Path) -> None:
    ticket = Path("demo/tickets/payment-reconciliation.md").read_text()
    diff = Path("demo/patches/risky-payment.diff").read_text()

    report = verify_change(ticket, diff, offline=True)
    paths = write_reports(report, tmp_path)

    assert report.verdict is Verdict.BLOCK
    assert report.risk_score == 100
    assert report.model_used is None
    assert len(report.findings) == 5
    assert all(path.exists() for path in paths.values())
    payload = json.loads(paths["json"].read_text())
    assert payload["evidence_hash"] == report.evidence_hash
    assert len(bytes.fromhex(report.evidence_hash)) == hashlib.sha256().digest_size
    assert "CodeTrust" in paths["html"].read_text()


def test_safe_change_passes() -> None:
    ticket = """## Outcome
- Rename internal display label.

## Acceptance criteria
- Updated label appears in the review screen.
"""
    diff = """diff --git a/ui/labels.py b/ui/labels.py
--- a/ui/labels.py
+++ b/ui/labels.py
@@ -1 +1 @@
-LABEL = "Pending"
+LABEL = "Awaiting review"
diff --git a/tests/test_labels.py b/tests/test_labels.py
--- /dev/null
+++ b/tests/test_labels.py
@@ -0,0 +1,2 @@
+def test_review_label():
+    assert LABEL == "Awaiting review"
"""

    report = verify_change(ticket, diff, offline=True)

    assert report.verdict is Verdict.PASS
    assert report.risk_score == 0


def test_low_risk_warning_does_not_force_human_review() -> None:
    report = verify_change(
        "## Outcome\n- Rename internal display label.\n",
        (
            "diff --git a/ui/labels.py b/ui/labels.py\n"
            "--- a/ui/labels.py\n"
            "+++ b/ui/labels.py\n"
            "@@ -1 +1 @@\n"
            '-LABEL = "Pending"\n'
            '+LABEL = "Awaiting review"\n'
        ),
        offline=True,
    )

    assert report.verdict is Verdict.PASS
    assert {item.rule_id for item in report.findings} == {"CT-TEST-002"}
    assert report.risk_score == 4


def test_unstructured_intent_never_passes() -> None:
    report = verify_change(
        "# Rename label",
        "diff --git a/a.c b/a.c\n--- a/a.c\n+++ b/a.c\n@@ -1 +1 @@\n-old\n+new\n",
        offline=True,
    )

    assert report.verdict is Verdict.NEEDS_REVIEW


def test_explicit_business_scope_drift_blocks_change() -> None:
    ticket = """# Payment retry telemetry

## In scope
- Emit retry counters for payment reconciliation.

## Out of scope
- Refund authorization behavior.

## Acceptance criteria
- Metrics only; refund policy must remain unchanged.
"""
    diff = """diff --git a/refunds/authorization.py b/refunds/authorization.py
--- a/refunds/authorization.py
+++ b/refunds/authorization.py
@@ -1 +1 @@
-    return order.age_days <= 30
+    return order.age_days <= 7
"""

    report = verify_change(
        ticket,
        diff,
        offline=True,
        interpretations=[
            InterpretationClaim(
                role="senior",
                text="Tighten refund authorization from 30 days to 7 days.",
                source="review",
            )
        ],
    )

    ids = {finding.rule_id for finding in report.findings}
    assert report.verdict is Verdict.BLOCK
    assert {"CT-SCOPE-001", "CT-INTERP-001"} <= ids
    assert report.scope_drift == 100
    assert report.unresolved_questions


def test_insufficient_repository_scope_forces_needs_review() -> None:
    report = verify_change(
        "## Outcome\n- Establish behavior from repository evidence.\n",
        (
            "diff --git a/ui/labels.py b/ui/labels.py\n"
            "--- a/ui/labels.py\n"
            "+++ b/ui/labels.py\n"
            "@@ -1 +1 @@\n"
            '-LABEL = "Pending"\n'
            '+LABEL = "Awaiting review"\n'
        ),
        offline=True,
        source={"intent_trust": "insufficient"},
        additional_questions=["Which base document defines this behavior?"],
    )

    assert report.verdict is Verdict.NEEDS_REVIEW
    assert report.intent == "Repository scope not established"
    assert "human review required" in report.summary
    assert report.unresolved_questions == ["Which base document defines this behavior?"]


def test_supported_inferred_scope_can_reach_scoped_pass() -> None:
    report = verify_change(
        """# Inferred scope from base repository

## Outcome
- Rename internal display label.

## Acceptance criteria
- Updated label appears in review screen.
""",
        """diff --git a/ui/labels.py b/ui/labels.py
--- a/ui/labels.py
+++ b/ui/labels.py
@@ -1 +1 @@
-LABEL = "Pending"
+LABEL = "Awaiting review"
diff --git a/tests/test_labels.py b/tests/test_labels.py
--- /dev/null
+++ b/tests/test_labels.py
@@ -0,0 +1,2 @@
+def test_review_label():
+    assert LABEL == "Awaiting review"
""",
        offline=True,
        source={"intent_source": "repository-inference", "intent_trust": "inferred"},
    )

    assert report.verdict is Verdict.PASS
    assert any("INFERRED scope" in event.detail for event in report.timeline)


def test_inferred_boundary_conflict_routes_to_review_not_approved_block() -> None:
    report = verify_change(
        """# Inferred scope from base repository

## Out of scope
- Refund authorization behavior.
""",
        """diff --git a/refunds/authorization.py b/refunds/authorization.py
--- a/refunds/authorization.py
+++ b/refunds/authorization.py
@@ -1 +1 @@
-return order.age_days <= 30
+return order.age_days <= 7
""",
        offline=True,
        source={"intent_source": "repository-inference", "intent_trust": "inferred"},
    )

    assert report.verdict is Verdict.NEEDS_REVIEW
    assert report.findings[0].rule_id == "CT-SCOPE-INFERRED-001"
    deterministic_findings = [
        item for item in report.findings if "-INFERRED-" not in item.rule_id
    ]
    assert report.risk_score == risk_score(deterministic_findings)
    assert report.risk_score < risk_score(report.findings)
    finding_text = " ".join(str(value) for value in report.findings[0].to_dict().values())
    assert "approved" not in finding_text.lower()


def test_large_repository_scope_distance_routes_to_review_and_stays_visible() -> None:
    comparison = ScopeComparison(
        repository_purpose="Provide accounting reports.",
        change_summary="Add operating-system theme management.",
        relationship="divergent",
        distance=82,
        differences=("Introduces desktop theme ownership.",),
        evidence_paths=("README", "src/reports.c"),
        rationale="Theme management sits outside accounting behavior.",
    )
    report = verify_change(
        """# Inferred scope from base repository

## Outcome
- Provide accounting reports.

## In scope
- Reporting behavior.
""",
        """diff --git a/ui/theme.c b/ui/theme.c
--- a/ui/theme.c
+++ b/ui/theme.c
@@ -1 +1 @@
-old_theme();
+manage_desktop_theme();
""",
        offline=True,
        source={"intent_source": "repository-inference", "intent_trust": "inferred"},
        scope_comparison=comparison,
    )

    assert report.verdict is Verdict.NEEDS_REVIEW
    assert report.scope_comparison == comparison
    assert report.to_dict()["scope_comparison"]["distance"] == 82
    markdown = render_markdown(report)
    rendered_html = render_html(report)
    assert "Repository-to-PR scope comparison" in markdown
    assert "Scope distance: **82/100**" in markdown
    assert "Introduces desktop theme ownership." in markdown
    assert "Repository baseline" in rendered_html
    assert "src/reports.c" in rendered_html
