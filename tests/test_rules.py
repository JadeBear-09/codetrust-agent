from pathlib import Path

from codetrust.diff_parser import parse_unified_diff
from codetrust.models import Severity
from codetrust.rules import risk_score, run_rules

DEMO_DIFF = Path("demo/patches/risky-payment.diff")


def test_demo_exposes_killer_risks() -> None:
    files = parse_unified_diff(DEMO_DIFF.read_text())

    findings, checks, skipped = run_rules(files)
    ids = {finding.rule_id for finding in findings}

    assert checks == [
        "secret-exposure",
        "debug-residue",
        "change-test-coverage",
        "async-safety",
        "payment-idempotency",
        "api-compatibility",
        "rollback-safety",
        "failure-coverage",
    ]
    assert skipped == []
    assert ids == {"CT-ASYNC-001", "CT-PAY-001", "CT-API-001", "CT-DB-001", "CT-TEST-001"}
    assert findings[0].severity is Severity.CRITICAL
    assert risk_score(findings) == 100


def test_idempotency_evidence_suppresses_payment_rule() -> None:
    diff = """diff --git a/payments.py b/payments.py
--- /dev/null
+++ b/payments.py
@@ -0,0 +1,5 @@
+def retry_payment(payment):
+    for attempt in range(3):
+        charge(payment, idempotency_key=payment.operation_id)
+        if payment.complete:
+            return
"""

    findings, _, _ = run_rules(parse_unified_diff(diff))

    assert "CT-PAY-001" not in {finding.rule_id for finding in findings}


def test_documentation_and_demo_fixtures_do_not_create_runtime_findings() -> None:
    diff = """diff --git a/docs/retry.md b/docs/retry.md
--- /dev/null
+++ b/docs/retry.md
@@ -0,0 +1 @@
+Retry payment charge without idempotency.
diff --git a/demo/payment.py b/demo/payment.py
--- /dev/null
+++ b/demo/payment.py
@@ -0,0 +1,3 @@
+def retry_payment(payment):
+    for attempt in range(3):
+        charge(payment)
"""

    findings, _, _ = run_rules(parse_unified_diff(diff))

    assert findings == []


def test_generic_gates_cover_c_and_redact_secrets() -> None:
    diff = '''diff --git a/src/config.c b/src/config.c
--- a/src/config.c
+++ b/src/config.c
@@ -1 +1,3 @@
-const char *mode = "safe";
+const char *mode = "debug";
+const char *api_key = "live-secret-value";
+breakpoint();
'''

    findings, applicable, _ = run_rules(parse_unified_diff(diff))
    ids = {finding.rule_id for finding in findings}

    assert {"CT-SEC-001", "CT-DEBUG-001", "CT-TEST-002"} <= ids
    assert "change-test-coverage" in applicable
    assert all("live-secret-value" not in finding.evidence for finding in findings)
