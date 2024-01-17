from datetime import timedelta

import asyncio

import pytest

from golem.utils.buffer import SimpleBuffer, Buffer, ExpirableBuffer, BackgroundFeedBuffer



@pytest.fixture
def mocked_buffer(mocker):
    return mocker.Mock(spec=Buffer)


def test_simple_buffer_creation():
    buffer = SimpleBuffer()
    assert buffer.size() == 0

    buffer = SimpleBuffer(["a", "b", "c"])
    assert buffer.size() == 3


async def test_simple_buffer_put_get():
    buffer = SimpleBuffer()
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
    buffer = SimpleBuffer()
    assert buffer.size() == 0

    _, pending = await asyncio.wait([buffer.get()], timeout=0.1)
    get_task = pending.pop()
    if not get_task:
        pytest.fail("Getting empty buffer somehow finished instead of blocking!")

    item_put = object()
    await buffer.put(item_put)

    item_get = await asyncio.wait_for(get_task, timeout=0.1)

    assert item_get == item_put


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


async def test_expirable_buffer_is_not_expiring_initial_items(mocked_buffer, mocker):
    expire_after = timedelta(seconds=0.1)
    ExpirableBuffer(
        mocked_buffer,
        lambda i: expire_after,
    )

    await asyncio.sleep(0.2)

    mocked_buffer.remove.assert_not_called()

async def test_expirable_buffer_is_not_expiring_items_with_none_expiration(mocked_buffer, mocker):
    expiration_func = mocker.Mock(side_effect=[
        timedelta(seconds=0.1),
        None,
        timedelta(seconds=0.1)
    ])
    buffer = ExpirableBuffer(
        mocked_buffer,
        expiration_func,
    )

    await buffer.put('a')
    await buffer.put('b')
    await buffer.put('c')

    await asyncio.sleep(0.2)

    assert mocker.call('a') in mocked_buffer.remove.mock_calls
    assert mocker.call('c') in mocked_buffer.remove.mock_calls

    mocked_buffer.get.return_value = 'b'

    assert await buffer.get() == 'b'


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
    mocked_buffer.put.assert_called_with(item_put)

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
    mocked_buffer.put.assert_called_with(item_put)

    await asyncio.sleep(0.2)

    mocked_buffer.remove.assert_called_with(item_put)
    on_expire.assert_called_with(item_put)


async def test_expirable_buffer_can_expire_items_with_put_all_get_all(mocked_buffer, mocker):
    expire_after = timedelta(seconds=0.1)
    on_expire = mocker.AsyncMock()
    buffer = ExpirableBuffer(
        mocked_buffer,
        lambda i: expire_after,
        on_expire,
    )
    items_put_all = ['a', 'b' , 'c']

    await buffer.put_all(items_put_all)
    mocked_buffer.put_all.assert_called_with(items_put_all)

    mocked_buffer.get_all.return_value = items_put_all
    await buffer.get_all()
    mocked_buffer.get_all.assert_called()

    mocked_buffer.remove.assert_not_called()
    on_expire.assert_not_called()

    await asyncio.sleep(0.2)

    on_expire.assert_not_called()

    mocked_buffer.reset_mock()

    await buffer.put_all(items_put_all)
    mocked_buffer.put_all.assert_called_with(items_put_all)

    await asyncio.sleep(0.2)

    assert mocker.call(items_put_all[0]) in mocked_buffer.remove.mock_calls
    assert mocker.call(items_put_all[1]) in mocked_buffer.remove.mock_calls
    assert mocker.call(items_put_all[2]) in mocked_buffer.remove.mock_calls

    assert mocker.call(items_put_all[0]) in on_expire.mock_calls
    assert mocker.call(items_put_all[1]) in on_expire.mock_calls
    assert mocker.call(items_put_all[2]) in on_expire.mock_calls


async def test_background_feed_buffer_start_stop(mocked_buffer, mocker):
    feed_func = mocker.AsyncMock()
    buffer = BackgroundFeedBuffer(
        mocked_buffer,
        feed_func,
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

    with pytest.raises(RuntimeError):
        await buffer.stop()

    assert not buffer.is_started()

    feed_func.assert_not_called()


async def test_background_feed_buffer_request(mocked_buffer, mocker):
    item = object()
    feed_queue = asyncio.Queue()
    feed_func = mocker.AsyncMock(wraps=feed_queue.get)
    buffer = BackgroundFeedBuffer(
        mocked_buffer,
        feed_func,
    )
    await buffer.start()

    await buffer.request(1)

    await asyncio.sleep(0.1)

    feed_func.assert_called()
    mocked_buffer.size.return_value = 0
    assert buffer.size() == 0
    assert buffer.size_with_requested() == 1

    await feed_queue.put(item)

    await asyncio.sleep(0.1)

    mocked_buffer.put.assert_called_with(item)
    mocked_buffer.size.return_value = 1
    assert buffer.size() == 1
    assert buffer.size_with_requested() == 1

    await buffer.stop()

async def test_background_feed_buffer_get_all_requested(mocked_buffer, mocker, event_loop):
    timeout = timedelta(seconds=0.1)
    item = object()
    feed_queue = asyncio.Queue()
    feed_func = mocker.AsyncMock(wraps=feed_queue.get)
    buffer = BackgroundFeedBuffer(
        mocked_buffer,
        feed_func,
    )
    await buffer.start()

    # Try to get items while buffer is empty and with no requests
    mocked_buffer.get_all.return_value = []
    mocked_buffer.size.return_value = 0

    time_before_wait = event_loop.time()
    assert await buffer.get_all_requested(timeout) == []
    time_after_wait = event_loop.time()

    assert time_after_wait - time_before_wait < timeout.total_seconds(), 'get_all_requested seems to wait for the deadline instead of retuning fast'
    #

    await buffer.request(1)

    await asyncio.sleep(0.1)

    feed_func.assert_called()
    mocked_buffer.size.return_value = 0
    assert buffer.size() == 0
    assert buffer.size_with_requested() == 1

    # Try to get items while buffer is empty but with pending requests
    mocked_buffer.get_all.return_value = []
    mocked_buffer.size.return_value = 0

    time_before_wait = event_loop.time()
    assert await buffer.get_all_requested(timeout) == []
    time_after_wait = event_loop.time()

    assert timeout.total_seconds() <= time_after_wait - time_before_wait, 'get_all_requested seems to not wait to the deadline'
    #

    await feed_queue.put(item)

    await asyncio.sleep(0.1)

    mocked_buffer.put.assert_called_with(item)
    mocked_buffer.size.return_value = 1
    assert buffer.size() == 1
    assert buffer.size_with_requested() == 1

    # Try to get items while buffer is have items and no pending requests
    mocked_buffer.get_all.return_value = [item]
    mocked_buffer.size.return_value = 0

    time_before_wait = event_loop.time()
    assert await buffer.get_all_requested(timeout) == [item]
    time_after_wait = event_loop.time()

    assert time_after_wait - time_before_wait < timeout.total_seconds(), 'get_all_requested seems to wait for the deadline instead of retuning fast'
    #

    await buffer.stop()
