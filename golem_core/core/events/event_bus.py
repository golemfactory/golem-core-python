import asyncio
from collections import defaultdict
from typing import Any, Awaitable, Callable, DefaultDict, Iterable, List, Optional, Type, TYPE_CHECKING

from golem_core.core.events.event import Event, TEvent
from golem_core.core.events.event_filters import EventFilter, AnyEventFilter

if TYPE_CHECKING:
    from golem_core.core.resources import TResourceEvent, Resource, ResourceEvent


class EventBus:
    """Emit events, listen for events.

    This class has few purposes:

    * Easy monitoring of the execution process (just log all events)
    * Convenient communication between separated parts of the code. E.g. we might want to act on incoming
      invoices from a component that is not connected to any other part of the code - with EventBus,
      we only have to register a callback for NewResource events.
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
        self.consumers: DefaultDict[EventFilter, List[Callable[[Any], Awaitable[None]]]] = defaultdict(list)

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
        callback: Callable[['TResourceEvent'], Awaitable[None]],
        event_classes: Iterable[Type['ResourceEvent']] = (),
        resource_classes: Iterable[Type['Resource']] = (),
        ids: Iterable[str] = (),
    ) -> None:
        """Execute the callback when :any:`ResourceEvent` is emitted.

        :param callback: An async function to be executed.
        :param event_classes: A list of :any:`ResourceEvent` subclasses - if not empty,
            `callback` will only be executed only on events of matching classes.
        :param resource_classes: A list of :class:`~golem_core.core.Resource` subclasses - if not empty,
            `callback` will only be executed on events related to core of a matching class.
        :param ids: A list of resource IDs - if not empty,
            `callback` will only be executed on events related to core with a matching ID.
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
