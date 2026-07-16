from __future__ import annotations

import asyncio

import structlog

from tnoc.bus import EventBus
from tnoc.db import create_engine, create_session_factory
from tnoc.observability import configure_observability, instrument_database
from tnoc.repository import Repository
from tnoc.settings import get_settings

log = structlog.get_logger()


async def serve() -> None:
    settings = get_settings()
    tracer_provider = configure_observability(settings, "outbox")
    engine = create_engine(settings)
    instrument_database(engine, tracer_provider)
    session_factory = create_session_factory(engine)
    bus = EventBus(settings)
    await bus.start()
    try:
        while True:
            claimed = 0
            async with session_factory() as session:
                repository = Repository(session, settings)
                records = await repository.claim_outbox(settings.outbox_batch_size)
                claimed = len(records)
                for record in records:
                    try:
                        await bus.publish(record.topic, record.message_key, record.payload)
                        await repository.mark_outbox_published(record)
                    except Exception as exc:
                        await repository.mark_outbox_failed(record, type(exc).__name__)
                        log.exception("outbox_publish_failed", outbox_id=str(record.id))
                        break
                await session.commit()
            if claimed == 0:
                await asyncio.sleep(settings.outbox_poll_interval_seconds)
    finally:
        await bus.stop()
        await engine.dispose()


def run() -> None:
    asyncio.run(serve())


if __name__ == "__main__":
    run()
