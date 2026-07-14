from __future__ import annotations

from codetrust.models import AdversarialTest, Finding

TEMPLATES: dict[str, tuple[str, str, str]] = {
    "CT-PAY-001": (
        "test_retry_is_idempotent",
        "Force timeout after provider-side success, retry same operation, and prove one side effect.",
        """def test_retry_is_idempotent(payment_service, provider):
    provider.succeed_then_timeout(operation_id="op-42")

    payment_service.reconcile(operation_id="op-42")

    assert provider.side_effect_count("op-42") == 1
""",
    ),
    "CT-ASYNC-001": (
        "test_concurrent_requests_do_not_block",
        "Delay provider I/O and prove concurrent work completes near one-request latency.",
        """async def test_concurrent_requests_do_not_block(service, slow_provider):
    slow_provider.delay_seconds = 0.2

    elapsed = await run_concurrently(service.reconcile, count=10)

    assert elapsed < 0.5
""",
    ),
    "CT-API-001": (
        "test_previous_contract_remains_accepted",
        "Replay last released client payload against changed contract.",
        """def test_previous_contract_remains_accepted(api_client, released_payload):
    response = api_client.post("/reconcile", json=released_payload)

    assert response.status_code < 400
""",
    ),
    "CT-DB-001": (
        "test_migration_round_trip",
        "Apply migration with in-flight data, roll back, and verify data plus schema.",
        """def test_migration_round_trip(database, migration):
    database.seed_in_flight_payment()
    migration.up(database)
    migration.down(database)

    assert database.matches_pre_migration_schema()
    assert database.in_flight_payment_exists()
""",
    ),
}


def generate_adversarial_tests(findings: list[Finding]) -> list[AdversarialTest]:
    tests: list[AdversarialTest] = []
    for finding in findings:
        template = TEMPLATES.get(finding.rule_id)
        if not template:
            continue
        name, rationale, code = template
        tests.append(
            AdversarialTest(
                rule_id=finding.rule_id,
                name=name,
                rationale=rationale,
                code=code,
            )
        )
    return tests
