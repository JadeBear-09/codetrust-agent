import hashlib
import json
from pathlib import Path

from codetrust.agent import verify_change
from codetrust.models import Verdict
from codetrust.report import write_reports


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
    ticket = "# Rename internal display label"
    diff = """diff --git a/ui/labels.py b/ui/labels.py
--- a/ui/labels.py
+++ b/ui/labels.py
@@ -1 +1 @@
-LABEL = "Pending"
+LABEL = "Awaiting review"
"""

    report = verify_change(ticket, diff, offline=True)

    assert report.verdict is Verdict.PASS
    assert report.risk_score == 0
