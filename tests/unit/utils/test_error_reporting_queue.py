import asyncio

import pytest

from golem.utils.queue import ErrorReportingQueue


class SomeException(Exception):
    ...


async def feed(q: ErrorReportingQueue, max_n: int, delay=0.01, raise_on_exit=True):
    n = 1
    while n <= max_n:
        q.put_nowait(n)
        n += 1
        await asyncio.sleep(delay)

    if raise_on_exit:
        q.set_exception(SomeException())


async def test_get():
    q = ErrorReportingQueue()
    retrieved = list()
    feed_task = asyncio.create_task(feed(q, 3, delay=0.01))
    for _ in range(3):
        retrieved.append(await q.get())

    assert retrieved == [1, 2, 3]

    with pytest.raises(SomeException):
        await q.get()

    feed_task.cancel()


async def test_get_nowait():
    q = ErrorReportingQueue()
    retrieved = list()
    feed_task = asyncio.create_task(feed(q, 5, delay=0.01))

    with pytest.raises(SomeException):
        for _ in range(667):  # the loop exits with an exception earlier anyway
            await asyncio.sleep(0.02)
            try:
                retrieved.append(q.get_nowait())
            except asyncio.QueueEmpty:
                pass

    assert retrieved == [1, 2, 3, 4, 5]

    feed_task.cancel()
