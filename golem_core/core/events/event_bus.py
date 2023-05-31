import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    DefaultDict,
    Iterable,
    List,
    Optional,
    Type,
)

from golem_core.core.events.base import Event
from golem_core.core.events.base import EventBus as BaseEventBus
from golem_core.core.events.base import EventBusError, TCallbackHandler, TEvent
from golem_core.core.events.event_filters import AnyEventFilter, EventFilter

if TYPE_CHECKING:
    from golem_core.core.resources import Resource, ResourceEvent, TResourceEvent


logger = logging.getLogger(__name__)


class EventBus:
    """Emit events, listen for events.

    This class has few purposes:

    * Easy monitoring of the execution process (just log all events)
    * Convenient communication between separated parts of the code. E.g. we might want to act on
      incoming invoices from a component that is not connected to any other part of the code - with
      EventBus, we only have to register a callback for NewResource events.
    * Using a producer-consumer pattern to implement parts of the app-specific logic.

    Sample usage::

        async def on_allocation_event(event: ResourceEvent) -> None:
            print(f"Something happened to an allocation!", event)

        golem = GolemNode()
        event_bus: EventBus = golem.event_bus
        event_bus.resource_listen(on_allocation_event, resource_classes=[Allocation])

        async with golem:
            #   This will cause execution of on_allocation_event with a NewResource event
            allocation = await golem.create_allocation(1)
        #   Allocation was created with autoclose=True, so now we also got a ResourceClosed event
    """

    def __init__(self) -> None:
        self.queue: asyncio.Queue[Event] = asyncio.Queue()
        self.consumers: DefaultDict[
            EventFilter, List[Callable[[Any], Awaitable[None]]]
        ] = defaultdict(list)

        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        assert self._task is None
        self._task = asyncio.create_task(self._emit_events())

    async def stop(self) -> None:
        if self._task:
            await self.queue.join()
            self._task.cancel()
            self._task = None

    def listen(
        self,
        callback: Callable[[TEvent], Awaitable[None]],
        classes: Iterable[Type[Event]] = (),
    ) -> None:
        """Execute the callback when :any:`Event` is emitted.

        :param callback: An async function to be executed.
        :param classes: A list of :any:`Event` subclasses - if not empty,
            `callback` will only be executed on events of matching classes.
        """
        template = AnyEventFilter(tuple(classes))
        self.consumers[template].append(callback)

    def resource_listen(
        self,
        callback: Callable[["TResourceEvent"], Awaitable[None]],
        event_classes: Iterable[Type["ResourceEvent"]] = (),
        resource_classes: Iterable[Type["Resource"]] = (),
        ids: Iterable[str] = (),
    ) -> None:
        """Execute the callback when :any:`ResourceEvent` is emitted.

        :param callback: An async function to be executed.
        :param event_classes: A list of :any:`ResourceEvent` subclasses - if not empty,
            `callback` will only be executed only on events of matching classes.
        :param resource_classes: A list of :class:`~golem_core.core.resources.Resource`
            subclasses - if not empty, `callback` will only be executed on events related to
            resources of a matching class.
        :param ids: A list of resource IDs - if not empty,
            `callback` will only be executed on events related to resources with a matching ID.
        """
        # FIXME: Get rid of local import
        from golem_core.core.resources.event_filters import ResourceEventFilter

        template = ResourceEventFilter(tuple(event_classes), tuple(resource_classes), tuple(ids))
        self.consumers[template].append(callback)

    def emit(self, event: Event) -> None:
        """Emit an event - execute all callbacks listening for matching events.

        If emit(X) was called before emit(Y), then it is guaranteed that callbacks
        for event Y will start only after all X callbacks finished (TODO - this should change,
        we don't want the EventBus to stop because of a single never-ending callback,
        https://github.com/golemfactory/golem-core-python/issues/3).

        :param event: An event that will be emitted.
        """
        self.queue.put_nowait(event)

    async def _emit_events(self) -> None:
        while True:
            event = await self.queue.get()
            await self._emit(event)

    async def _emit(self, event: Event) -> None:
        #   TODO: https://github.com/golemfactory/golem-core-python/issues/3
        tasks = []
        for event_template, callbacks in self.consumers.items():
            if event_template.includes(event):
                tasks += [callback(event) for callback in callbacks]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.queue.task_done()


@dataclass
class _CallbackInfo:
    callback: Callable[[TEvent], Awaitable[None]]
    filter_func: Optional[Callable[[TEvent], bool]]
    once: bool


class InMemoryEventBus(BaseEventBus):
    def __init__(self):
        self._callbacks: DefaultDict[Type[TEvent], List[_CallbackInfo]] = defaultdict(list)
        self._event_queue = asyncio.Queue()
        self._process_event_queue_loop_task: Optional[asyncio.Task] = None

    async def start(self):
        logger.debug("Starting event bus...")

        if self.is_started():
            message = "Event bus is already started!"
            logger.debug(f"Starting event bus failed with `{message}`")
            raise EventBusError(message)

        self._process_event_queue_loop_task = asyncio.create_task(self._process_event_queue_loop())

        logger.debug("Starting event bus done")

    async def stop(self):
        logger.debug("Stopping event bus...")

        if not self.is_started():
            message = "Event bus is not started!"
            logger.debug(f"Stopping event bus failed with `{message}`")
            raise EventBusError(message)

        await self._event_queue.join()

        self._process_event_queue_loop_task.cancel()
        self._process_event_queue_loop_task = None

        logger.debug("Stopping event bus done")

    def is_started(self) -> bool:
        return self._process_event_queue_loop_task is not None

    async def on(
        self,
        event_type: Type[TEvent],
        callback: Callable[[TEvent], Awaitable[None]],
        filter_func: Optional[Callable[[TEvent], bool]] = None,
    ) -> TCallbackHandler:
        logger.debug(
            f"Adding callback handler for `{event_type}` with callback `{callback}` and filter `{filter_func}`..."
        )

        callback_info = _CallbackInfo(
            callback=callback,
            filter_func=filter_func,
            once=False,
        )

        self._callbacks[event_type].append(callback_info)

        callback_handler = (event_type, callback_info)

        logger.debug(f"Adding callback handler done with `{id(callback_handler)}`")

        return callback_handler

    async def on_once(
        self,
        event_type: Type[TEvent],
        callback: Callable[[TEvent], Awaitable[None]],
        filter_func: Optional[Callable[[TEvent], bool]] = None,
    ) -> TCallbackHandler:
        logger.debug(
            f"Adding one-time callback handler for `{event_type}` with callback `{callback}` and filter `{filter_func}`..."
        )

        callback_info = _CallbackInfo(
            callback=callback,
            filter_func=filter_func,
            once=True,
        )

        self._callbacks[event_type].append(callback_info)

        callback_handler = (event_type, callback_info)

        logger.debug(f"Adding one-time callback handler done with `{id(callback_handler)}`")

        return callback_handler

    async def off(self, callback_handler: TCallbackHandler) -> None:
        logger.debug(f"Removing callback handler `{id(callback_handler)}`...")

        event_type, callback_info = callback_handler

        try:
            self._callbacks[event_type].remove(callback_info)
        except (KeyError, ValueError):
            message = "Given callback handler is not found in event bus!"
            logger.debug(
                f"Removing callback handler `{id(callback_handler)}` failed with `{message}`"
            )
            raise EventBusError(message)

        logger.debug(f"Removing callback handler `{id(callback_handler)}` done")

    async def emit(self, event: TEvent) -> None:
        logger.debug(f"Emitting event `{event}`...")

        if not self.is_started():
            message = "Event bus is not started!"
            logger.debug(f"Emitting event `{event}` failed with `message`")
            raise EventBusError(message)

        await self._event_queue.put(event)

        logger.debug(f"Emitting event `{event}` done")

    async def _process_event_queue_loop(self):
        while True:
            logger.debug("Getting event from queue...")

            event = await self._event_queue.get()

            logger.debug(f"Getting event from queue done with `{event}`")

            logger.debug(f"Processing callbacks for event `{event}`...")

            for event_type, callback_infos in self._callbacks.items():
                await self._process_event(event, event_type, callback_infos)

            logger.debug(f"Processing callbacks for event `{event}` done")

            self._event_queue.task_done()

    async def _process_event(
        self, event: Event, event_type: Type[Event], callback_infos: List[_CallbackInfo]
    ):
        logger.debug(f"Processing event `{event}` on event type `{event_type}`...")

        if not isinstance(event, event_type):
            logger.debug(
                f"Processing event `{event}` on event type `{event_type}` ignored as event is not a instance of event type"
            )
            return

        callback_infos_to_remove = []

        logger.debug(f"Processing callbacks for event {event}...")

        for callback_info in callback_infos:
            logger.debug(f"Processing callback {callback_info}...")

            if callback_info.filter_func is not None:
                logger.debug("Calling filter function...")
                try:
                    if not callback_info.filter_func(event):
                        logger.debug("Calling filter function done, ignoring callback")
                        continue
                except:
                    logger.exception(
                        f"Encountered an error in `{callback_info.filter_func}` filter function while handling `{event}`!"
                    )
                    continue
                else:
                    logger.debug("Calling filter function done, calling callback")
            else:
                logger.debug("Callback has no filter function")

            logger.debug(f"Calling {callback_info.callback}...")
            try:
                await callback_info.callback(event)
            except Exception as e:
                logger.debug(f"Calling {callback_info.callback} failed with `{e}")

                logger.exception(
                    f"Encountered an error in `{callback_info.callback}` callback while handling `{event}`!"
                )
                continue
            else:
                logger.debug(f"Calling {callback_info.callback} done")

            if callback_info.once:
                callback_infos_to_remove.append(callback_info)

                logger.debug(f"Callback {callback_info} marked as to be removed")

        logger.debug(f"Processing callbacks for event {event} done")

        if callback_infos_to_remove:
            logger.debug(f"Removing callbacks `{callback_infos_to_remove}`...")

            for callback_info in callback_infos_to_remove:
                callback_infos.remove(callback_info)

            logger.debug(f"Removing callbacks `{callback_infos_to_remove}` done")

        logger.debug(f"Processing event `{event}` on event type `{event_type}` done")
