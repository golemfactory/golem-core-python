import asyncio

import pytest

from golem.utils.asyncio import Waiter


async def test_waiter_single_wait_for():
    waiter = Waiter()
    value = 0

    wait_task = asyncio.create_task(waiter.wait_for(lambda: value == 1))

    await asyncio.sleep(0.1)

    assert not wait_task.done()

    waiter.notify()

    await asyncio.sleep(0.1)

    assert not wait_task.done()

    value = 1
    waiter.notify()

    await asyncio.wait_for(wait_task, timeout=0.1)


async def test_waiter_multiple_wait_for():
    waiter = Waiter()
    value = 0

    wait_task1 = asyncio.create_task(waiter.wait_for(lambda: value == 1))
    wait_task2 = asyncio.create_task(waiter.wait_for(lambda: value == 1))
    wait_task3 = asyncio.create_task(waiter.wait_for(lambda: value == 1))

    await asyncio.sleep(0.1)

    assert not wait_task1.done()

    value = 1
    waiter.notify()

    await asyncio.wait_for(wait_task1, timeout=0.1)

    done, _ = await asyncio.wait([wait_task2, wait_task3], timeout=0.1)

    if done:
        pytest.fail("Somehow some tasks finished too early!")

    waiter.notify(2)

    _, pending = await asyncio.wait([wait_task2, wait_task3], timeout=0.1)

    if pending:
        pytest.fail("Somehow some tasks not finished!")


async def test_waiter_will_renotify_when_predicate_was_false():
    waiter = Waiter()
    value = 0

    wait_task1 = asyncio.create_task(waiter.wait_for(lambda: value == 2))
    wait_task2 = asyncio.create_task(waiter.wait_for(lambda: value == 1))

    await asyncio.sleep(0.1)
    assert not wait_task2.done() and not wait_task1.done()

    value = 1
    waiter.notify()

    await asyncio.sleep(0.1)

    assert wait_task2.done(), "Task2 should be done at this point!"
    assert not wait_task1.done(), "Task1 should still block at this point!"

    value = 2

    waiter.notify()

    await asyncio.wait_for(wait_task1, timeout=0.1)
