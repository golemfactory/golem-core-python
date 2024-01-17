import asyncio
import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import timedelta
from typing import (
    Awaitable,
    Callable,
    Dict,
    Generic,
    Iterable,
    List,
    MutableSequence,
    Optional,
    Sequence,
    TypeVar,
)

from golem.utils.asyncio import cancel_and_await_many, create_task_with_logging
from golem.utils.logging import get_trace_id_name, trace_span
from golem.utils.semaphore import SingleUseSemaphore

TItem = TypeVar("TItem")

logger = logging.getLogger(__name__)


class Buffer(ABC, Generic[TItem]):
    @abstractmethod
    def size(self) -> int:
        """Return number of items stored in buffer."""
        ...

    @abstractmethod
    async def wait_for_any_items(self) -> None:
        """Wait until any items are stored in buffer."""
        ...

    @abstractmethod
    async def get(self) -> TItem:
        """Await, remove and return left-most item stored in buffer."""
        ...

    @abstractmethod
    async def get_all(self) -> MutableSequence[TItem]:
        """Remove and return all items stored in buffer."""
        ...

    @abstractmethod
    async def put(self, item: TItem) -> None:
        """Add item to right-most position to buffer.

        Duplicates are supported.
        """
        ...

    @abstractmethod
    async def put_all(self, items: Sequence[TItem]) -> None:
        """Replace all items stored in buffer.

        Duplicates are supported.
        """
        ...

    @abstractmethod
    async def remove(self, item: TItem) -> None:
        """Remove first occurrence of item from buffer or raise `ValueError` if not found."""
        ...


class ComposableBuffer(Buffer[TItem]):
    """Utility class for composable/stackable buffer implementations to help with calling underlying buffer."""

    def __init__(self, buffer: Buffer[TItem]):
        self._buffer = buffer

    def size(self) -> int:
        return self._buffer.size()

    async def wait_for_any_items(self) -> None:
        await self._buffer.wait_for_any_items()

    async def get(self) -> TItem:
        return await self._buffer.get()

    async def get_all(self) -> MutableSequence[TItem]:
        return await self._buffer.get_all()

    async def put(self, item: TItem) -> None:
        await self._buffer.put(item)

    async def put_all(self, items: Sequence[TItem]) -> None:
        await self._buffer.put_all(items)

    async def remove(self, item: TItem) -> None:
        await self._buffer.remove(item)


class SimpleBuffer(Buffer[TItem]):
    """Most basic implementation of Buffer interface."""

    def __init__(self, items: Optional[Sequence[TItem]] = None):
        self._items = list(items) if items is not None else []

        self._have_items = (
            asyncio.Event()
        )  # TODO: collections of future-object waiters instead of event

        if self.size():
            self._have_items.set()

    def size(self) -> int:
        return len(self._items)

    async def wait_for_any_items(self) -> None:
        while not self.size():
            await self._have_items.wait()

    async def get(self) -> TItem:
        await self.wait_for_any_items()

        item = self._items.pop(0)

        if not self.size():
            self._have_items.clear()

        return item

    async def get_all(self) -> MutableSequence[TItem]:
        items = self._items[:]
        self._items.clear()
        self._have_items.clear()
        return items

    async def put(self, item: TItem) -> None:
        self._items.append(item)
        self._have_items.set()

    async def put_all(self, items: Sequence[TItem]) -> None:
        self._items.clear()
        self._items.extend(items[:])

        if self.size():
            self._have_items.set()
        else:
            self._have_items.clear()

    async def remove(self, item: TItem) -> None:
        self._items.remove(item)

        if not self.size():
            self._have_items.clear()


class ExpirableBuffer(ComposableBuffer[TItem]):
    """Composable that adds option to expire item after some time.

    Items that are already in provided buffer will not expire.
    """

    # TODO: Optimisation options: Use single expiration task that wakes up to expire the earliest item,
    #  then check next earliest item and sleep to it and repeat

    def __init__(
        self,
        buffer: Buffer[TItem],
        get_expiration_func: Callable[[TItem], Optional[timedelta]],
        on_expiration_func: Optional[Callable[[TItem], Awaitable[None]]] = None,
    ):
        super().__init__(buffer)

        self._get_expiration_func = get_expiration_func
        self._on_expiration_func = on_expiration_func

        # Lock is used to keep items in buffer and expiration tasks in sync
        self._lock = asyncio.Lock()
        self._expiration_handlers: Dict[int, List[asyncio.TimerHandle]] = defaultdict(list)

    def _add_expiration_task_for_item(self, item: TItem) -> None:
        expiration = self._get_expiration_func(item)

        if expiration is None:
            return

        loop = asyncio.get_event_loop()

        self._expiration_handlers[id(item)].append(
            loop.call_later(expiration.total_seconds(), lambda: asyncio.create_task(self._expire_item(item)))
        )

    async def _remove_expiration_handler_for_item(self, item: TItem) -> None:
        item_id = id(item)

        if item_id not in self._expiration_handlers or not len(self._expiration_handlers[item_id]):
            return

        expiration_handle = self._expiration_handlers[item_id].pop(0)
        expiration_handle.cancel()

        if not self._expiration_handlers[item_id]:
            del self._expiration_handlers[item_id]

    async def _remove_all_expiration_handlers(self) -> None:
        for handlers in self._expiration_handlers.values():
            for handler in handlers:
                handler.cancel()

        self._expiration_handlers.clear()

    async def get(self) -> Iterable[TItem]:
        async with self._lock:
            item = await super().get()
            await self._remove_expiration_handler_for_item(item)

            return item

    async def get_all(self) -> MutableSequence[TItem]:
        async with self._lock:
            items = await super().get_all()
            await self._remove_all_expiration_handlers()
            return items

    async def put(self, item: TItem) -> None:
        async with self._lock:
            await super().put(item)
            self._add_expiration_task_for_item(item)

    async def put_all(self, items: Sequence[TItem]) -> None:
        async with self._lock:
            await super().put_all(items)
            await self._remove_all_expiration_handlers()

            for item in items:
                self._add_expiration_task_for_item(item)

    async def remove(self, item: TItem) -> None:
        async with self._lock:
            await super().remove(item)
            await self._remove_expiration_handler_for_item(item)

    async def _expire_item(self, item: TItem) -> None:
        await self.remove(item)

        if self._on_expiration_func:
            await self._on_expiration_func(item)


class BackgroundFeedBuffer(ComposableBuffer[TItem]):
    """Composable that adds option to feed buffer in background task.

    Background feed will happen only if background tasks are started by calling `.start()`
    and items were requested by `.request()`.
    """

    def __init__(
        self,
        buffer: Buffer[TItem],
        feed_func: Callable[[], Awaitable[TItem]],
        feed_concurrency_size=1,
    ):
        super().__init__(buffer)

        self._feed_func = feed_func
        self._feed_concurrency_size = feed_concurrency_size

        self._is_started = False
        self._worker_tasks: List[asyncio.Task] = []
        self._workers_semaphore = SingleUseSemaphore()

    @trace_span()
    async def start(self) -> None:
        if self.is_started():
            raise RuntimeError("Already started!")

        for i in range(self._feed_concurrency_size):
            self._worker_tasks.append(
                create_task_with_logging(
                    self._worker_loop(), trace_id=get_trace_id_name(self, f"worker-{i}")
                )
            )

        self._is_started = True

    @trace_span()
    async def stop(self) -> None:
        if not self.is_started():
            raise RuntimeError("Already stopped!")

        await cancel_and_await_many(self._worker_tasks)
        self._worker_tasks.clear()
        self._is_started = False

        self._workers_semaphore.reset()

    def is_started(self) -> bool:
        return self._is_started

    async def _worker_loop(self):
        while True:
            async with self._workers_semaphore:
                item = await self._feed_func()

                await self.put(item)

    async def request(self, count: int) -> None:
        """Request given number of items to be filled in background."""
        await self._workers_semaphore.increase(count)

    def size_with_requested(self) -> int:
        """Return sum of items stored in buffer and requested to be filled."""
        return self.size() + self._workers_semaphore.get_count_with_pending()

    async def get_all_requested(self, deadline: timedelta) -> MutableSequence[TItem]:
        """Await for all requested items with given deadline, then remove and return all items stored in buffer."""
        try:
            await asyncio.wait_for(
                self._workers_semaphore.finished.wait(), deadline.total_seconds()
            )
        except asyncio.TimeoutError:
            pass

        return await self.get_all()
