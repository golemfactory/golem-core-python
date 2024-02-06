import asyncio
from datetime import timedelta

import pytest

from golem.utils.asyncio.buffer import BackgroundFillBuffer, Buffer, ExpirableBuffer, SimpleBuffer


@pytest.fixture
def mocked_buffer(mocker):
    mock = mocker.Mock(spec=Buffer)

    mock.condition = mocker.AsyncMock()

    return mock


def test_simple_buffer_creation():
    buffer: Buffer[str] = SimpleBuffer()
    assert buffer.size() == 0

    buffer = SimpleBuffer(["a", "b", "c"])
    assert buffer.size() == 3


async def test_simple_buffer_put_get():
    buffer: Buffer[object] = SimpleBuffer()
    assert buffer.size() == 0

    item_put = object()

    await buffer.put(item_put)

    assert buffer.size() == 1

    item_get = await buffer.get()

    assert buffer.size() == 0

    assert item_put == item_get


async def test_simple_buffer_put_all_get_all():
    buffer = SimpleBuffer(["a"])
    assert buffer.size() == 1

    await buffer.put_all(["b", "c", "d"])
    assert buffer.size() == 3

    assert await buffer.get_all() == ["b", "c", "d"]

    assert buffer.size() == 0

    assert await buffer.get_all() == []


async def test_simple_buffer_remove():
    buffer = SimpleBuffer(["a", "b", "c"])

    await buffer.remove("b")

    assert await buffer.get_all() == ["a", "c"]


async def test_simple_buffer_get_waits_for_items():
    buffer: Buffer[object] = SimpleBuffer()
    assert buffer.size() == 0

    _, pending = await asyncio.wait([asyncio.create_task(buffer.get())], timeout=0.1)
    if not pending:
        pytest.fail("Getting empty buffer somehow finished instead of blocking!")

    get_task = pending.pop()

    item_put = object()
    await buffer.put(item_put)

    item_get = await asyncio.wait_for(get_task, timeout=0.1)

    assert item_get == item_put

    # concurrent wait
    get_task1 = asyncio.create_task(buffer.get())
    get_task2 = asyncio.create_task(buffer.get())

    await asyncio.sleep(0.1)

    await buffer.put(item_put)

    done, pending = await asyncio.wait([get_task1, get_task2], timeout=0.1)
    if len(done) != len(pending):
        pytest.fail("One of the tasks should not block at this point!")

    await buffer.put(item_put)

    await asyncio.sleep(0.1)

    await asyncio.wait_for(pending.pop(), timeout=0.1)


async def test_simple_buffer_keeps_item_order():
    buffer = SimpleBuffer(["a", "b", "c"])

    assert await buffer.get() == "a"
    assert await buffer.get() == "b"
    assert await buffer.get() == "c"

    await buffer.put("d")
    await buffer.put("e")
    await buffer.put("f")

    assert await buffer.get() == "d"
    assert await buffer.get_all() == ["e", "f"]


async def test_simple_buffer_keeps_shallow_copy_of_items():
    initial_items = ["a", "b", "c"]
    buffer = SimpleBuffer(initial_items)
    assert buffer.size() == 3

    initial_items.extend(["d", "e", "f"])
    assert buffer.size() == 3

    put_items = ["g", "h", "i"]
    await buffer.put_all(put_items)
    assert buffer.size() == 3

    put_items.extend(["j", "k", "l"])
    assert buffer.size() == 3


async def test_simple_buffer_exceptions():
    buffer: Buffer[str] = SimpleBuffer()
    assert buffer.size() == 0

    exc = ZeroDivisionError()

    await buffer.set_exception(exc)

    # should raise when exception set and no items
    with pytest.raises(ZeroDivisionError):
        await buffer.get()

    with pytest.raises(ZeroDivisionError):
        await buffer.get_all()

    await buffer.put("a")

    # should not raise when exception set and with items
    assert await buffer.get_all() == ["a"]

    # should raise when exception set and items were cleared
    with pytest.raises(ZeroDivisionError):
        await buffer.get_all()

    buffer.reset_exception()

    assert await buffer.get_all() == []

    try:
        await asyncio.wait_for(buffer.get(), timeout=0.1)
    except asyncio.TimeoutError:
        pass
    else:
        pytest.fail("Getting empty buffer somehow finished instead of blocking!")

    get_task = asyncio.create_task(buffer.get())

    await asyncio.sleep(0.1)

    await buffer.set_exception(exc)

    await asyncio.sleep(0.1)

    with pytest.raises(ZeroDivisionError):
        get_task.result()


async def test_simple_buffer_wait_for_any_items():
    buffer: Buffer[str] = SimpleBuffer()
    assert buffer.size() == 0

    # should block on empty
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(buffer.wait_for_any_items(), timeout=0.1)

    # should unblock on item
    wait_task = asyncio.create_task(buffer.wait_for_any_items())

    await asyncio.sleep(0.1)

    assert not wait_task.done()

    await buffer.put("a")

    await asyncio.sleep(0.1)

    assert wait_task.done()

    # should not block a long time on item
    await asyncio.wait_for(buffer.wait_for_any_items(), timeout=0.1)

    await buffer.set_exception(ZeroDivisionError())

    # should not block a long time on item with exception
    await asyncio.wait_for(buffer.wait_for_any_items(), timeout=0.1)

    await buffer.get()

    # should raise with exception and no items
    with pytest.raises(ZeroDivisionError):
        await asyncio.wait_for(buffer.wait_for_any_items(), timeout=0.1)

    buffer.reset_exception()

    # should block on after exception reset and no items
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(buffer.wait_for_any_items(), timeout=0.1)

    # should unblock on item
    wait_task = asyncio.create_task(buffer.wait_for_any_items())

    await asyncio.sleep(0.1)

    assert not wait_task.done()

    await buffer.set_exception(ZeroDivisionError())

    await asyncio.sleep(0.1)

    assert wait_task.done()


async def test_expirable_buffer_is_not_expiring_initial_items(mocked_buffer):
    expire_after = timedelta(seconds=0.1)
    ExpirableBuffer(
        mocked_buffer,
        lambda i: expire_after,
    )

    await asyncio.sleep(0.2)

    mocked_buffer.remove.assert_not_called()


async def test_expirable_buffer_is_not_expiring_items_with_none_expiration(mocked_buffer, mocker):
    expiration_func = mocker.Mock(
        side_effect=[timedelta(seconds=0.1), None, timedelta(seconds=0.1)]
    )
    buffer = ExpirableBuffer(
        mocked_buffer,
        expiration_func,
    )

    await buffer.put("a")
    await buffer.put("b")
    await buffer.put("c")

    await asyncio.sleep(0.2)

    assert mocker.call("a", lock=False) in mocked_buffer.remove.mock_calls
    assert mocker.call("c", lock=False) in mocked_buffer.remove.mock_calls

    mocked_buffer.get.return_value = "b"

    assert await buffer.get() == "b"


async def test_expirable_buffer_can_expire_items_with_put_get(mocked_buffer, mocker):
    expire_after = timedelta(seconds=0.1)
    on_expire = mocker.AsyncMock()
    buffer = ExpirableBuffer(
        mocked_buffer,
        lambda i: expire_after,
        on_expire,
    )
    item_put = object()

    await buffer.put(item_put)
    mocked_buffer.put.assert_called_with(item_put, lock=False)

    mocked_buffer.get.return_value = item_put
    await buffer.get()
    mocked_buffer.get.assert_called()

    mocked_buffer.remove.assert_not_called()
    on_expire.assert_not_called()

    await asyncio.sleep(0.2)

    mocked_buffer.remove.assert_not_called()
    on_expire.assert_not_called()

    mocked_buffer.reset_mock()

    await buffer.put(item_put)
    mocked_buffer.put.assert_called_with(item_put, lock=False)

    await asyncio.sleep(0.2)

    mocked_buffer.remove.assert_called_with(item_put, lock=False)
    on_expire.assert_called_with(item_put)


async def test_expirable_buffer_can_expire_items_with_put_all_get_all(mocked_buffer, mocker):
    expire_after = timedelta(seconds=0.1)
    on_expire = mocker.AsyncMock()
    buffer = ExpirableBuffer(
        mocked_buffer,
        lambda i: expire_after,
        on_expire,
    )
    items_put_all = ["a", "b", "c"]

    await buffer.put_all(items_put_all)
    mocked_buffer.put_all.assert_called_with(items_put_all, lock=False)

    mocked_buffer.get_all.return_value = items_put_all
    await buffer.get_all()
    mocked_buffer.get_all.assert_called_with(lock=False)

    with pytest.raises(AssertionError):
        mocked_buffer.remove.assert_called_with(lock=False)

    on_expire.assert_not_called()

    await asyncio.sleep(0.2)

    on_expire.assert_not_called()

    mocked_buffer.reset_mock()

    await buffer.put_all(items_put_all)
    mocked_buffer.put_all.assert_called_with(items_put_all, lock=False)

    await asyncio.sleep(0.2)

    assert mocker.call(items_put_all[0], lock=False) in mocked_buffer.remove.mock_calls
    assert mocker.call(items_put_all[1], lock=False) in mocked_buffer.remove.mock_calls
    assert mocker.call(items_put_all[2], lock=False) in mocked_buffer.remove.mock_calls

    assert mocker.call(items_put_all[0]) in on_expire.mock_calls
    assert mocker.call(items_put_all[1]) in on_expire.mock_calls
    assert mocker.call(items_put_all[2]) in on_expire.mock_calls


async def test_background_fill_buffer_start_stop(mocked_buffer, mocker):
    fill_func = mocker.AsyncMock()
    buffer = BackgroundFillBuffer(
        mocked_buffer,
        fill_func,
    )

    assert not buffer.is_started()

    await buffer.start()

    assert buffer.is_started()

    with pytest.raises(RuntimeError):
        await buffer.start()

    assert buffer.is_started()
    mocked_buffer.size.return_value = 0
    assert buffer.size_with_requested() == 0

    await buffer.stop()

    assert not buffer.is_started()

    await buffer.stop()

    assert not buffer.is_started()

    fill_func.assert_not_called()


async def test_background_fill_buffer_request(mocked_buffer, mocker):
    item = object()
    fill_queue: asyncio.Queue[object] = asyncio.Queue()
    fill_func = mocker.AsyncMock(wraps=fill_queue.get)
    on_added_func = mocker.AsyncMock()
    buffer = BackgroundFillBuffer(
        mocked_buffer,
        fill_func,
        on_added_func=on_added_func,
    )
    await buffer.start()

    await buffer.request(1)

    await asyncio.sleep(0.1)

    fill_func.assert_called()
    mocked_buffer.size.return_value = 0
    assert buffer.size() == 0
    assert buffer.size_with_requested() == 1

    await fill_queue.put(item)

    await asyncio.sleep(0.1)

    mocked_buffer.put.assert_called_with(item, lock=True)
    mocked_buffer.size.return_value = 1
    on_added_func.assert_called()
    assert buffer.size() == 1
    assert buffer.size_with_requested() == 1

    await buffer.stop()


async def test_background_fill_buffer_fill_exception(mocked_buffer, mocker):
    event = asyncio.Event()
    exc = ZeroDivisionError()

    async def fill_func():
        await event.wait()
        raise exc

    on_added_func = mocker.AsyncMock()
    buffer = BackgroundFillBuffer(
        mocked_buffer,
        fill_func,
        on_added_func=on_added_func,
    )
    await buffer.start()

    await buffer.request(1)

    await asyncio.sleep(0.1)

    mocked_buffer.size.return_value = 0
    assert buffer.size() == 0
    assert buffer.size_with_requested() == 1

    event.set()

    await asyncio.sleep(0.1)

    mocked_buffer.put.assert_not_called()
    mocked_buffer.set_exception.assert_called_with(exc, lock=True)
    mocked_buffer.size.return_value = 0
    on_added_func.assert_not_called()
    assert buffer.size() == 0
    assert buffer.size_with_requested() == 0
    assert not buffer.is_started()


async def test_background_fill_buffer_get_requested(mocked_buffer, mocker, event_loop):
    timeout = timedelta(seconds=0.1)
    item = object()
    fill_queue: asyncio.Queue[object] = asyncio.Queue()
    fill_func = mocker.AsyncMock(wraps=fill_queue.get)
    buffer = BackgroundFillBuffer(
        mocked_buffer,
        fill_func,
    )
    await buffer.start()

    # Try to get items while buffer is empty and with no requests
    mocked_buffer.get_all.return_value = []
    mocked_buffer.size.return_value = 0

    time_before_wait = event_loop.time()
    assert await buffer.get_requested(timeout) == []
    time_after_wait = event_loop.time()

    assert (
        time_after_wait - time_before_wait < timeout.total_seconds()
    ), "get_requested seems to wait for the deadline instead of retuning fast"
    #

    await buffer.request(1)

    await asyncio.sleep(0.1)

    fill_func.assert_called()
    mocked_buffer.size.return_value = 0
    assert buffer.size() == 0
    assert buffer.size_with_requested() == 1

    # Try to get items while buffer is empty but with pending requests
    mocked_buffer.get_all.return_value = []
    mocked_buffer.size.return_value = 0

    time_before_wait = event_loop.time()
    assert await buffer.get_requested(timeout) == []
    time_after_wait = event_loop.time()

    assert (
        timeout.total_seconds() <= time_after_wait - time_before_wait
    ), "get_requested seems to not wait to the deadline"
    #

    await fill_queue.put(item)

    await asyncio.sleep(0.1)

    mocked_buffer.put.assert_called_with(item, lock=True)
    mocked_buffer.size.return_value = 1
    assert buffer.size() == 1
    assert buffer.size_with_requested() == 1

    # Try to get items while buffer is have items and no pending requests
    mocked_buffer.get_all.return_value = [item]
    mocked_buffer.size.return_value = 0

    time_before_wait = event_loop.time()
    assert await buffer.get_requested(timeout) == [item]
    time_after_wait = event_loop.time()

    assert (
        time_after_wait - time_before_wait < timeout.total_seconds()
    ), "get_requested seems to wait for the deadline instead of retuning fast"
    #

    await buffer.stop()
