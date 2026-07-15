from codetrust.diff_parser import parse_unified_diff
from codetrust.models import AlignmentStatus
from codetrust.scope import analyze_scope, parse_intent_snapshot


def test_parses_structured_product_intent() -> None:
    snapshot = parse_intent_snapshot(
        """# Checkout resilience

## Goal
Prevent duplicate customer charges.

## In scope
- Payment retry handling.

## Non-goals
- Refund authorization policy.

## Acceptance criteria
1. One operation creates at most one charge.
"""
    )

    assert snapshot.outcome == ("Prevent duplicate customer charges.",)
    assert snapshot.in_scope == ("Payment retry handling.",)
    assert snapshot.out_of_scope == ("Refund authorization policy.",)
    assert snapshot.acceptance_criteria == ("One operation creates at most one charge.",)


def test_explicit_out_of_scope_change_is_contradicted() -> None:
    ticket = """## Out of scope
- Refund authorization behavior.
"""
    diff = """diff --git a/refunds/authorization.py b/refunds/authorization.py
--- a/refunds/authorization.py
+++ b/refunds/authorization.py
@@ -1 +1 @@
-return order.age_days <= 30
+return order.age_days <= 7
"""

    result = analyze_scope(ticket, parse_unified_diff(diff))

    assert result.findings[0].rule_id == "CT-SCOPE-001"
    assert result.alignments[0].status is AlignmentStatus.CONTRADICTED
    assert result.drift == 100
