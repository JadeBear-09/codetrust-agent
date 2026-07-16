from __future__ import annotations

import asyncio

from alembic import command
from alembic.config import Config
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from tnoc.settings import get_settings


async def setup_checkpoints(connection_string: str) -> None:
    async with AsyncPostgresSaver.from_conn_string(connection_string) as checkpointer:
        await checkpointer.setup()


def run() -> None:
    settings = get_settings()
    command.upgrade(Config("alembic.ini"), "head")
    asyncio.run(setup_checkpoints(settings.checkpoint_database_url))


if __name__ == "__main__":
    run()
