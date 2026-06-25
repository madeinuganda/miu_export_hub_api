"""Wait until PostgreSQL accepts connections. Used by Docker entrypoint."""
from __future__ import annotations

import os
import sys
import time

from sqlalchemy import create_engine, text

MAX_ATTEMPTS = 60
SLEEP_SECONDS = 1


def sync_database_url(url: str) -> str:
    """Use a sync driver for connectivity checks (works with any DATABASE_URL format)."""
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    return url


def wait() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        sys.exit(1)

    url = sync_database_url(url)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            engine = create_engine(url, pool_pre_ping=True)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            engine.dispose()
            print(f"Database ready (attempt {attempt})")
            return
        except Exception as exc:
            print(f"Waiting for database ({attempt}/{MAX_ATTEMPTS}): {exc}")
            time.sleep(SLEEP_SECONDS)

    print("Database not ready in time", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    wait()
