from pathlib import Path

from codetrust.diff_parser import parse_unified_diff
from codetrust.models import Severity
from codetrust.rules import risk_score, run_rules

DEMO_DIFF = Path("demo/patches/risky-payment.diff")


def test_demo_exposes_killer_risks() -> None:
    files = parse_unified_diff(DEMO_DIFF.read_text())

    findings, checks = run_rules(files)
    ids = {finding.rule_id for finding in findings}

    assert checks == [
        "async-safety",
        "payment-idempotency",
        "api-compatibility",
        "rollback-safety",
        "failure-coverage",
    ]
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

    findings, _ = run_rules(parse_unified_diff(diff))

    assert "CT-PAY-001" not in {finding.rule_id for finding in findings}
