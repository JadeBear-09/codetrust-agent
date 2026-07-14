import asyncio

import httpx


async def reconcile_payment(payment, client: httpx.AsyncClient, operation_id: str):
    headers = {"Idempotency-Key": operation_id}
    for attempt in range(3):
        try:
            response = await client.post(
                "https://provider.example/reconcile",
                json={"payment_id": payment.id, "amount": payment.amount},
                headers=headers,
                timeout=5,
            )
            response.raise_for_status()
            payment.status = "reconciled"
            return payment
        except httpx.TimeoutException:
            await asyncio.sleep(2**attempt)
    raise RuntimeError("reconciliation failed")
