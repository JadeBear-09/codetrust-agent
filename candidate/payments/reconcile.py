import asyncio

import requests


async def reconcile_payment(payment):
    for attempt in range(3):
        try:
            response = requests.post(
                "https://provider.example/reconcile",
                json={"payment_id": payment.id, "amount": payment.amount},
                timeout=5,
            )
            response.raise_for_status()
            payment.status = "reconciled"
            return payment
        except requests.Timeout:
            await asyncio.sleep(2**attempt)
    raise RuntimeError("reconciliation failed")
