from __future__ import annotations

from typing import Any

import orjson
from aiokafka import AIOKafkaProducer

from tnoc.settings import Settings


class EventBus:
    def __init__(self, settings: Settings) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_serializer=orjson.dumps,
            key_serializer=lambda value: value.encode("utf-8"),
            enable_idempotence=True,
            acks="all",
        )

    async def start(self) -> None:
        await self._producer.start()

    async def stop(self) -> None:
        await self._producer.stop()

    async def publish(self, topic: str, key: str, payload: dict[str, Any]) -> None:
        await self._producer.send_and_wait(topic, key=key, value=payload)
