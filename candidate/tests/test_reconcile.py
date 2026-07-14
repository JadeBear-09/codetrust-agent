from candidate.payments.reconcile import reconcile_payment


async def test_reconcile_success(payment, provider):
    provider.respond(status=200)

    result = await reconcile_payment(payment)

    assert result.status == "reconciled"
    assert provider.call_count == 1
