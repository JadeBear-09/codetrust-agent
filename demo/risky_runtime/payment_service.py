from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Payment:
    payment_id: str
    amount: int
    status: str = "pending"


class TimeoutAfterSuccessProvider:
    """Provider commits first call but client sees timeout."""

    def __init__(self) -> None:
        self.side_effects: list[str] = []

    def reconcile(self, payment: Payment) -> None:
        self.side_effects.append(payment.payment_id)
        if len(self.side_effects) == 1:
            raise TimeoutError("response lost after provider commit")


async def reconcile_payment(
    payment: Payment,
    provider: TimeoutAfterSuccessProvider,
) -> Payment:
    for _attempt in range(3):
        try:
            provider.reconcile(payment)
            payment.status = "reconciled"
            return payment
        except TimeoutError:
            continue
    raise RuntimeError("reconciliation failed")
