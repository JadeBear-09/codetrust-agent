from codetrust.models import Finding, Severity
from codetrust.testgen import generate_adversarial_tests


def test_generates_idempotency_proof() -> None:
    finding = Finding(
        rule_id="CT-PAY-001",
        title="missing idempotency",
        severity=Severity.CRITICAL,
        confidence=0.9,
        path="payments.py",
        line=1,
        evidence="charge(payment)",
        impact="duplicate charge",
        challenge="prove one charge",
        suggested_test="timeout after success",
    )

    tests = generate_adversarial_tests([finding])

    assert tests[0].name == "test_retry_is_idempotent"
    assert "side_effect_count" in tests[0].code
