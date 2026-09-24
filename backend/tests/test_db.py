import asyncio
import os
from datetime import date

import pytest

from app.db import create_pool, check_and_increment

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://askquiz:askquiz@localhost:5433/askquiz"
)


@pytest.fixture
async def pool():
    db_pool = await create_pool(TEST_DATABASE_URL)
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM usage")
    yield db_pool
    await db_pool.close()


async def test_allows_requests_up_to_cap(pool):
    device_id = "device-a"
    today = date(2026, 9, 24)
    for _ in range(3):
        allowed = await check_and_increment(pool, device_id, cap=3, today=today)
        assert allowed is True


async def test_rejects_requests_over_cap(pool):
    device_id = "device-b"
    today = date(2026, 9, 24)
    for _ in range(3):
        await check_and_increment(pool, device_id, cap=3, today=today)
    allowed = await check_and_increment(pool, device_id, cap=3, today=today)
    assert allowed is False


async def test_cap_resets_on_a_new_date(pool):
    device_id = "device-c"
    for _ in range(3):
        await check_and_increment(pool, device_id, cap=3, today=date(2026, 9, 24))
    allowed_next_day = await check_and_increment(
        pool, device_id, cap=3, today=date(2026, 9, 25)
    )
    assert allowed_next_day is True


async def test_concurrent_requests_never_exceed_cap(pool):
    device_id = "device-d"
    today = date(2026, 9, 24)
    results = await asyncio.gather(
        *[check_and_increment(pool, device_id, cap=3, today=today) for _ in range(10)]
    )
    assert sum(results) == 3
