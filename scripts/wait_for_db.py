"""Wait until PostgreSQL accepts connections. Used by Docker entrypoint."""
from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

MAX_ATTEMPTS = 60
SLEEP_SECONDS = 1


async def wait() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        sys.exit(1)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            engine = create_async_engine(url, pool_pre_ping=True)
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            await engine.dispose()
            print(f"Database ready (attempt {attempt})")
            return
        except Exception as exc:
            print(f"Waiting for database ({attempt}/{MAX_ATTEMPTS}): {exc}")
            await asyncio.sleep(SLEEP_SECONDS)

    print("Database not ready in time", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    asyncio.run(wait())
