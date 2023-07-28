from abc import ABC, abstractmethod
from typing import Awaitable, Callable, Generic, Optional, Type, TypeVar

from golem.exceptions import GolemException

TCallbackHandler = TypeVar("TCallbackHandler")

TEvent = TypeVar("TEvent", bound="Event")


class Event(ABC):
    """Base class for all events."""


class EventBusError(GolemException):
    pass


class EventBus(ABC, Generic[TCallbackHandler]):
    @abstractmethod
    async def start(self) -> None:
        ...

    @abstractmethod
    async def stop(self) -> None:
        ...

    @abstractmethod
    def is_started(self) -> bool:
        ...

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
        self,
        event_type: Type[TEvent],
        callback: Callable[[TEvent], Awaitable[None]],
        filter_func: Optional[Callable[[TEvent], bool]] = None,
    ) -> TCallbackHandler:
        ...

    @abstractmethod
    async def off(self, callback_handler: TCallbackHandler) -> None:
        ...

    @abstractmethod
    async def emit(self, event: TEvent) -> None:
        ...
