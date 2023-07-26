import asyncio
from datetime import timedelta

import pytest

from golem.utils.buffer import ConcurrentlyFilledBuffer


@pytest.fixture
def fill_callback(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def buffer_class():
    return ConcurrentlyFilledBuffer


@pytest.fixture
def create_buffer(fill_callback, buffer_class):
    def _create_buffer(*args, **kwargs):
        return buffer_class(
            fill_callback=fill_callback,
            *args,
            **kwargs,
        )

    return _create_buffer


async def test_buffer_start_stop(create_buffer):
    buffer = create_buffer(min_size=0, max_size=0)

    assert not buffer.is_started()

    with pytest.raises(RuntimeError, match="Already stopped!"):
        await buffer.stop()

    with pytest.raises(RuntimeError, match="Not started!"):
        await buffer.get_item()

    await buffer.start()

    with pytest.raises(RuntimeError, match="Already started!"):
        await buffer.start()

    assert buffer.is_started()

    await buffer.stop()

    assert not buffer.is_started()


async def test_buffer_will_block_on_empty(create_buffer):
    buffer = create_buffer(min_size=0, max_size=0)

    await buffer.start()

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(buffer.get_item(), 0.1)

    await buffer.stop()


@pytest.mark.parametrize(
    "min_size, max_size, fill, await_count",
    (
        (3, 10, False, 0),
        (3, 10, True, 10),
        (3, 5, True, 5),
    ),
)
async def test_buffer_start_with_fill(
    create_buffer, fill_callback, min_size, max_size, fill, await_count
):
    buffer = create_buffer(min_size=min_size, max_size=max_size)

    await buffer.start(fill=fill)

    await asyncio.sleep(0.01)

    assert fill_callback.await_count == await_count

    await buffer.stop()


async def test_buffer_get_item_will_on_empty_will_trigger_fill(create_buffer, fill_callback):
    buffer = create_buffer(min_size=3, max_size=10)

    await buffer.start()

    await asyncio.sleep(0.01)

    assert fill_callback.await_count == 0

    item = await asyncio.wait_for(buffer.get_item(), 0.05)

    assert item == fill_callback.mock_calls[0]

    assert fill_callback.await_count == 10

    await buffer.stop()


async def test_buffer_get_item_will_trigger_fill_on_below_min_size(create_buffer, fill_callback):
    buffer = create_buffer(min_size=3, max_size=10)

    await buffer.start(fill=True)

    await asyncio.sleep(0.01)

    assert fill_callback.await_count == 10

    item = await asyncio.wait_for(buffer.get_item(), 0.05)

    assert item == fill_callback.mock_calls[0]

    assert fill_callback.await_count == 10

    done, _ = await asyncio.wait(
        [asyncio.ensure_future(buffer.get_item()) for _ in range(6)], timeout=0.05
    )

    assert [d.result() for d in done] == fill_callback.mock_calls[1:7]

    assert fill_callback.await_count == 10

    item = await asyncio.wait_for(buffer.get_item(), 0.05)

    assert item == fill_callback.mock_calls[8]

    assert fill_callback.await_count == 18

    await buffer.stop()


async def test_buffer_fill_can_add_requests_while_other_requests_are_running(
    buffer_class, mocker, caplog
):
    queue: asyncio.Queue[int] = asyncio.Queue()

    for i in range(3):
        await queue.put(i)

    async def fill_callback():
        item = await queue.get()
        queue.task_done()
        return item

    mocked_fill_callback = mocker.AsyncMock(wraps=fill_callback)

    buffer = buffer_class(
        fill_callback=mocked_fill_callback,
        min_size=3,
        max_size=6,
        update_interval=timedelta(seconds=0.05),
    )

    await buffer.start(fill=True)

    await asyncio.sleep(0.1)

    assert mocked_fill_callback.await_count == 6

    item = await asyncio.wait_for(buffer.get_item(), 0.05)

    assert item == 0

    assert mocked_fill_callback.await_count == 7

    await buffer.stop()

    assert len(asyncio.all_tasks()) == 1, "Other async tasks are running!"


# TODO: Expiration needs to be implemented
async def _test_buffer_can_expire_elements(create_buffer, fill_callback):
    buffer = create_buffer(min_size=3, max_size=6, remove_after=timedelta(seconds=0.5))

    await buffer.start(fill=True)

    await asyncio.sleep(0.1)

    assert fill_callback.await_count == 6

    await asyncio.sleep(0.5)

    assert fill_callback.await_count == 12

    await buffer.stop()

    assert len(asyncio.all_tasks()) == 1, "Other async tasks are running!"
