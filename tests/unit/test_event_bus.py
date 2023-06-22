import logging
import logging.config

import pytest

from golem_core.core.events.base import Event, EventBusError
from golem_core.core.events.event_bus import InMemoryEventBus
from golem_core.utils.logging import DEFAULT_LOGGING


class ExampleEvent(Event):
    pass


class ParamExampleEvent(Event):
    def __init__(self, val):
        self.val = val


@pytest.fixture(autouse=True)
async def logs():
    logging.config.dictConfig(DEFAULT_LOGGING)


@pytest.fixture
async def event_bus(caplog):
    event_bus = InMemoryEventBus()

    await event_bus.start()

    yield event_bus

    if event_bus.is_started():
        await event_bus.stop()


async def test_start_stop():
    event_bus = InMemoryEventBus()

    await event_bus.start()

    assert event_bus.is_started()

    with pytest.raises(EventBusError, match="already started"):
        await event_bus.start()

    await event_bus.stop()

    assert not event_bus.is_started()

    with pytest.raises(EventBusError, match="not started"):
        await event_bus.stop()


async def test_on_off(mocker):
    event_bus = InMemoryEventBus()

    callback_mock = mocker.Mock()

    callback_handler = await event_bus.on(ExampleEvent, callback_mock)

    await event_bus.off(callback_handler)

    with pytest.raises(EventBusError, match="callback handler is not found"):
        await event_bus.off(callback_handler)


async def test_emit_raises_while_not_started():
    event_bus = InMemoryEventBus()

    assert not event_bus.is_started()

    with pytest.raises(EventBusError, match="not started"):
        await event_bus.emit(ExampleEvent())


async def test_emit_multiple(mocker, event_bus):
    callback_mock = mocker.Mock()

    await event_bus.on(ExampleEvent, callback_mock)

    event1 = ExampleEvent()
    event2 = ExampleEvent()
    event3 = ExampleEvent()

    await event_bus.emit(event1)
    await event_bus.emit(event2)
    await event_bus.emit(event3)

    await event_bus.stop()  # Waits for all callbacks to be called

    assert callback_mock.mock_calls == [
        mocker.call(event1),
        mocker.call(event2),
        mocker.call(event3),
    ]


async def test_emit_once(mocker, event_bus):
    callback_mock = mocker.AsyncMock()

    callback_handler = await event_bus.on_once(ExampleEvent, callback_mock)

    event1 = ExampleEvent()
    event2 = ExampleEvent()
    event3 = ExampleEvent()

    await event_bus.emit(event1)
    await event_bus.emit(event2)
    await event_bus.emit(event3)

    await event_bus.stop()  # Waits for all callbacks to be called

    callback_mock.assert_called_once_with(event1)

    with pytest.raises(EventBusError, match="callback handler is not found"):
        await event_bus.off(callback_handler)


async def test_emit_with_filter(mocker, event_bus):
    callback_mock = mocker.Mock()
    callback_mock_once = mocker.Mock()

    await event_bus.on(ParamExampleEvent, callback_mock, lambda e: e.val == 2)
    await event_bus.on_once(ParamExampleEvent, callback_mock_once, lambda e: e.val == 3)

    event1 = ParamExampleEvent(1)
    event2 = ParamExampleEvent(2)
    event3 = ParamExampleEvent(3)

    await event_bus.emit(event1)
    await event_bus.emit(event2)
    await event_bus.emit(event3)

    await event_bus.stop()  # Waits for all callbacks to be called

    assert callback_mock.mock_calls == [
        mocker.call(event2),
    ]

    assert callback_mock_once.mock_calls == [
        mocker.call(event3),
    ]


async def test_emit_with_errors(mocker, caplog, event_bus):
    callback_mock = mocker.Mock(side_effect=Exception)

    await event_bus.on(ExampleEvent, callback_mock)
    await event_bus.on(ParamExampleEvent, callback_mock, lambda e: e.not_existing)

    event1 = ExampleEvent()
    event2 = ParamExampleEvent(2)

    caplog.at_level(logging.ERROR)

    caplog.clear()
    await event_bus.emit(event1)
    await event_bus.stop()  # Waits for all callbacks to be called

    assert "callback while handling" in caplog.text

    await event_bus.start()

    caplog.clear()
    await event_bus.emit(event2)
    await event_bus.stop()  # Waits for all callbacks to be called

    assert "filter function while handling" in caplog.text
