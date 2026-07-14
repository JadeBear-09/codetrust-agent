from candidate.payments.reconcile import reconcile_payment


async def test_timeout_retry_reuses_idempotency_key(payment, provider):
    provider.timeout_after_success_once()

    await reconcile_payment(payment, provider, operation_id="op-42")

    assert provider.idempotency_keys == ["op-42", "op-42"]
    assert provider.side_effect_count("op-42") == 1


async def test_concurrent_reconciliation_remains_non_blocking(service):
    results = await service.reconcile_concurrently(count=10)

    assert len(results) == 10


def test_migration_rollback_preserves_in_flight_payment(database, migration):
    migration.up(database)
    migration.rollback(database)

    assert database.in_flight_payment_exists()
