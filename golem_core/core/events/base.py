from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from typing import Awaitable, Callable, DefaultDict, List, Optional, Type, TypeVar

TEvent = TypeVar("TEvent", bound="Event")


class Event(ABC):
    """Base class for all events."""


TCallbackHandler = TypeVar("TCallbackHandler")


class EventBus(ABC):
    @abstractmethod
    async def on(
        self,
        event_type: Type[TEvent],
        callback: Callable[[TEvent], Awaitable[None]],
        filter_func: Optional[Callable[[TEvent], bool]] = None,
    ) -> TCallbackHandler:
        ...

    @abstractmethod
    async def on_once(
        self, event_type: Type[TEvent], callback: Callable[[TEvent], Awaitable[None]]
    ) -> TCallbackHandler:
        ...

    @abstractmethod
    async def off(self, callback_handler: TCallbackHandler) -> None:
        ...

    @abstractmethod
    async def emit(self, event: TEvent) -> None:
        ...


@dataclass
class CallbackInfo:
    callback: Callable[[TEvent], Awaitable[None]]
    filter_func: Optional[Callable[[TEvent], bool]]
    once: bool


class InMemoryEventBus(EventBus):
    def __init__(self):
        self._callbacks: DefaultDict[Type[TEvent], List[CallbackInfo]] = defaultdict(list)

    async def on(
        self,
        event_type: Type[TEvent],
        callback: Callable[[TEvent], Awaitable[None]],
        filter_func: Optional[Callable[[TEvent], bool]] = None,
    ) -> TCallbackHandler:
        callback_info = CallbackInfo(
            callback=callback,
            filter_func=filter_func,
            once=False,
        )

        self._callbacks[event_type].append(callback_info)

        return (event_type, callback_info)

    async def on_once(
        self,
        event_type: Type[TEvent],
        callback: Callable[[TEvent], Awaitable[None]],
        filter_func: Optional[Callable[[TEvent], bool]] = None,
    ) -> TCallbackHandler:
        callback_info = CallbackInfo(
            callback=callback,
            filter_func=filter_func,
            once=True,
        )

        self._callbacks[event_type].append(callback_info)

        return (event_type, callback_info)

    async def off(self, callback_handler: TCallbackHandler) -> None:
        event_type, callback_info = callback_handler

        try:
            self._callbacks[event_type].remove(callback_info)
        except (KeyError, ValueError):
            raise ValueError(f"Given callback handler is not found in event bus!")

    async def emit(self, event: TEvent) -> None:
        for event_type, callback_infos in self._callbacks.items():
            if not isinstance(event, event_type):
                continue

            callback_infos_copy = callback_infos[:]

            for callback_info in callback_infos_copy:
                if callback_info.filter_func is not None and not callback_info.filter_func(event):
                    continue

                callback_info.callback(event)

                if callback_info.once:
                    callback_infos.remove(callback_info)
