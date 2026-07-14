import asyncio

from demo.risky_runtime.payment_service import (
    Payment,
    TimeoutAfterSuccessProvider,
    reconcile_payment,
)


def test_timeout_after_success_does_not_duplicate_payment() -> None:
    payment = Payment(payment_id="pay-42", amount=4999)
    provider = TimeoutAfterSuccessProvider()

    result = asyncio.run(reconcile_payment(payment, provider))

    assert result.status == "reconciled"
    assert provider.side_effects.count("pay-42") == 1
