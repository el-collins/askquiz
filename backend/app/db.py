from datetime import date

import asyncpg

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS usage (
    device_id TEXT NOT NULL,
    date DATE NOT NULL,
    request_count INT NOT NULL DEFAULT 0,
    PRIMARY KEY (device_id, date)
);
"""


async def create_pool(database_url: str) -> asyncpg.Pool:
    pool = await asyncpg.create_pool(database_url)
    async with pool.acquire() as conn:
        await conn.execute(CREATE_TABLE_SQL)
    return pool


async def check_and_increment(
    pool: asyncpg.Pool, device_id: str, cap: int, today: date
) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO usage (device_id, date, request_count)
            VALUES ($1, $2, 1)
            ON CONFLICT (device_id, date)
            DO UPDATE SET request_count = usage.request_count + 1
            RETURNING request_count
            """,
            device_id,
            today,
        )
    return row["request_count"] <= cap
