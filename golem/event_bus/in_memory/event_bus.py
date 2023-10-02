import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Awaitable, Callable, DefaultDict, List, Optional, Tuple, Type

from golem.event_bus.base import Event, EventBus, EventBusError, TEvent
from golem.utils.asyncio import create_task_with_logging
from golem.utils.logging import get_trace_id_name, trace_span

logger = logging.getLogger(__name__)


@dataclass
class _CallbackInfo:
    callback: Callable[[TEvent], Awaitable[None]]
    filter_func: Optional[Callable[[TEvent], bool]]
    once: bool


_CallbackHandler = Tuple[Type[TEvent], _CallbackInfo]


class InMemoryEventBus(EventBus[_CallbackHandler]):
    def __init__(self):
        self._callbacks: DefaultDict[Type[Event], List[_CallbackInfo]] = defaultdict(list)
        self._event_queue: asyncio.Queue[Event] = asyncio.Queue()
        self._process_event_queue_loop_task: Optional[asyncio.Task] = None

    @trace_span()
    async def start(self):
        if self.is_started():
            message = "Event bus is already started!"
            logger.debug(f"Starting event bus failed with `{message}`")
            raise EventBusError(message)

        self._process_event_queue_loop_task = create_task_with_logging(
            self._process_event_queue_loop(),
            trace_id=get_trace_id_name(self, "process-event-queue-loop"),
        )

    @trace_span()
    async def stop(self):
        if not self.is_started():
            message = "Event bus is not started!"
            logger.debug(f"Stopping event bus failed with `{message}`")
            raise EventBusError(message)

        await self._event_queue.join()

        if self._process_event_queue_loop_task is not None:
            self._process_event_queue_loop_task.cancel()
            self._process_event_queue_loop_task = None

    @trace_span(show_results=True)
    def is_started(self) -> bool:
        return (
            self._process_event_queue_loop_task is not None
            and not self._process_event_queue_loop_task.done()
        )

    @trace_span(show_arguments=True)
    async def on(
        self,
        event_type: Type[TEvent],
        callback: Callable[[TEvent], Awaitable[None]],
        filter_func: Optional[Callable[[TEvent], bool]] = None,
    ) -> _CallbackHandler:
        callback_info = _CallbackInfo(
            callback=callback,
            filter_func=filter_func,
            once=False,
        )

        self._callbacks[event_type].append(callback_info)

        callback_handler = (event_type, callback_info)

        return callback_handler

    @trace_span(show_arguments=True)
    async def on_once(
        self,
        event_type: Type[TEvent],
        callback: Callable[[TEvent], Awaitable[None]],
        filter_func: Optional[Callable[[TEvent], bool]] = None,
    ) -> _CallbackHandler:
        callback_info = _CallbackInfo(
            callback=callback,
            filter_func=filter_func,
            once=True,
        )

        self._callbacks[event_type].append(callback_info)

        callback_handler = (event_type, callback_info)

        return callback_handler

    @trace_span(show_arguments=True)
    async def off(self, callback_handler: _CallbackHandler) -> None:
        event_type, callback_info = callback_handler
        try:
            self._callbacks[event_type].remove(callback_info)
        except (KeyError, ValueError):
            message = "Given callback handler is not found in event bus!"
            logger.debug(
                f"Removing callback handler `{id(callback_handler)}` failed with `{message}`"
            )
            raise EventBusError(message)

    @trace_span(show_arguments=True)
    async def emit(self, event: TEvent) -> None:
        if not self.is_started():
            message = "Event bus is not started!"
            logger.debug(f"Emitting event `{event}` failed with `message`")
            raise EventBusError(message)

        await self._event_queue.put(event)

    async def _process_event_queue_loop(self):
        while True:
            logger.debug("Getting event from queue...")
            event = await self._event_queue.get()
            logger.debug(f"Getting event from queue done with `{event}`")

            for event_type, callback_infos in self._callbacks.items():
                await self._process_event(event, event_type, callback_infos)

            self._event_queue.task_done()

    @trace_span(show_arguments=True)
    async def _process_event(
        self, event: Event, event_type: Type[Event], callback_infos: List[_CallbackInfo]
    ):
        if not isinstance(event, event_type):
            logger.debug(
                f"Processing event `{event}` on event type `{event_type}` ignored as event is"
                f" not a instance of event type"
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
                except Exception:
                    logger.exception(
                        f"Encountered an error in `{callback_info.filter_func}` filter function"
                        f" while handling `{event}`!"
                    )
                    continue
                else:
                    logger.debug("Calling filter function done, calling callback")
            else:
                logger.debug("Callback has no filter function")

            logger.debug(f"Calling {callback_info.callback}...")
            try:
                # TODO: Support sync callbacks
                await callback_info.callback(event)
            except Exception as e:
                logger.debug(f"Calling {callback_info.callback} failed with `{e}")

                logger.exception(
                    f"Encountered an error in `{callback_info.callback}` callback"
                    f" while handling `{event}`!"
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
