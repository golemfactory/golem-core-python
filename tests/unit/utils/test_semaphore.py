import asyncio

import pytest

from golem.utils.asyncio.semaphore import SingleUseSemaphore


async def test_creation():
    sem = SingleUseSemaphore()

    assert sem.get_count() == 0
    assert sem.get_count_with_pending() == 0
    assert sem.get_pending_count() == 0
    assert sem.finished.is_set()
    assert sem.locked()

    sem = SingleUseSemaphore(0)

    assert sem.get_count() == 0
    assert sem.get_count_with_pending() == 0
    assert sem.get_pending_count() == 0
    assert sem.finished.is_set()
    assert sem.locked()

    sem_count = 10
    sem = SingleUseSemaphore(sem_count)

    assert sem.get_count() == sem_count
    assert sem.get_count_with_pending() == sem_count
    assert sem.get_pending_count() == 0
    assert not sem.finished.is_set()
    assert not sem.locked()

    with pytest.raises(ValueError):
        SingleUseSemaphore(-10)


async def test_increase():
    sem = SingleUseSemaphore()

    assert sem.get_count() == 0
    assert sem.get_count_with_pending() == 0
    assert sem.get_pending_count() == 0
    assert sem.finished.is_set()
    assert sem.locked()

    await sem.increase(1)

    assert sem.get_count() == 1
    assert sem.get_count_with_pending() == 1
    assert sem.get_pending_count() == 0
    assert not sem.finished.is_set()
    assert not sem.locked()

    await sem.increase(10)

    assert sem.get_count() == 11
    assert sem.get_count_with_pending() == 11
    assert sem.get_pending_count() == 0
    assert not sem.finished.is_set()
    assert not sem.locked()


async def test_reset():
    sem_value = 10
    sem = SingleUseSemaphore(sem_value)

    assert sem.get_count() == sem_value
    assert sem.get_count_with_pending() == sem_value
    assert sem.get_pending_count() == 0
    assert not sem.finished.is_set()
    assert not sem.locked()

    sem.reset()

    assert sem.get_count() == 0
    assert sem.get_count_with_pending() == 0
    assert sem.get_pending_count() == 0
    assert not sem.finished.is_set()
    assert sem.locked()


async def test_acquire():
    sem_value = 1
    sem = SingleUseSemaphore(sem_value)

    assert sem.get_count() == sem_value
    assert sem.get_count_with_pending() == sem_value
    assert sem.get_pending_count() == 0
    assert not sem.finished.is_set()
    assert not sem.locked()

    await asyncio.wait_for(sem.acquire(), 0.1)

    assert sem.get_count() == 0
    assert sem.get_count_with_pending() == 1
    assert sem.get_pending_count() == 1
    assert not sem.finished.is_set()
    assert sem.locked()

    _, pending = await asyncio.wait([asyncio.create_task(sem.acquire())], timeout=0.1)
    acquire_task = pending.pop()
    if not acquire_task:
        pytest.fail("Acquiring locked semaphore somehow finished instead of blocking!")

    await sem.increase(1)

    assert sem.get_count() == 1
    assert sem.get_count_with_pending() == 2
    assert sem.get_pending_count() == 1
    assert not sem.finished.is_set()
    assert not sem.locked()

    await asyncio.wait_for(acquire_task, 0.1)

    assert sem.get_count() == 0
    assert sem.get_count_with_pending() == 2
    assert sem.get_pending_count() == 2
    assert not sem.finished.is_set()
    assert sem.locked()


async def test_release():
    sem_value = 1
    sem = SingleUseSemaphore(sem_value)

    assert sem.get_count() == sem_value
    assert sem.get_count_with_pending() == sem_value
    assert sem.get_pending_count() == 0
    assert not sem.finished.is_set()
    assert not sem.locked()

    with pytest.raises(RuntimeError):
        sem.release()

    await asyncio.wait_for(sem.acquire(), 0.1)

    assert sem.get_count() == 0
    assert sem.get_count_with_pending() == 1
    assert sem.get_pending_count() == 1
    assert not sem.finished.is_set()
    assert sem.locked()

    sem.release()

    assert sem.get_count() == 0
    assert sem.get_count_with_pending() == 0
    assert sem.get_pending_count() == 0
    assert sem.finished.is_set()
    assert sem.locked()


async def test_context_manager():
    sem_value = 2
    sem = SingleUseSemaphore(sem_value)

    assert sem.get_count() == sem_value
    assert sem.get_count_with_pending() == sem_value
    assert sem.get_pending_count() == 0
    assert not sem.finished.is_set()
    assert not sem.locked()

    async with sem:
        assert sem.get_count() == 1
        assert sem.get_count_with_pending() == sem_value
        assert sem.get_pending_count() == 1
        assert not sem.finished.is_set()
        assert not sem.locked()

    assert sem.get_count() == 1
    assert sem.get_count_with_pending() == 1
    assert sem.get_pending_count() == 0
    assert not sem.finished.is_set()
    assert not sem.locked()

    async with sem:
        assert sem.get_count() == 0
        assert sem.get_count_with_pending() == 1
        assert sem.get_pending_count() == 1
        assert not sem.finished.is_set()
        assert sem.locked()

    assert sem.get_count() == 0
    assert sem.get_count_with_pending() == 0
    assert sem.get_pending_count() == 0
    assert sem.finished.is_set()
    assert sem.locked()
