import asyncio
import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import (
    Awaitable,
    Callable,
    Dict,
    Generic,
    List,
    MutableSequence,
    Optional,
    Sequence,
    TypeVar,
)

from golem.utils.asyncio.semaphore import SingleUseSemaphore
from golem.utils.asyncio.tasks import (
    cancel_and_await_many,
    create_task_with_logging,
    resolve_maybe_awaitable,
)
from golem.utils.logging import get_trace_id_name, trace_span
from golem.utils.typing import MaybeAwaitable

TItem = TypeVar("TItem")

logger = logging.getLogger(__name__)


class Buffer(ABC, Generic[TItem]):
    """Interface class for object similar to `asyncio.Queue` but with more control over its \
    items."""

    condition: asyncio.Condition

    @abstractmethod
    def size(self) -> int:
        """Return number of items stored in buffer."""

    @abstractmethod
    async def wait_for_any_items(self, *, lock=True) -> None:
        """Wait until any items are stored in buffer."""

    @abstractmethod
    async def get(self, *, lock=True) -> TItem:
        """Await, remove and return left-most item stored in buffer.

        If `.set_exception()` was previously called, exception will be raised only if buffer
        is empty.
        """

    @abstractmethod
    async def get_all(self, *, lock=True) -> MutableSequence[TItem]:
        """Remove and return all items stored in buffer.

        Note that this method will not await for any items if buffer is empty.

        If `.set_exception()` was previously called, exception will be raised only if buffer
        is empty.
        """

    @abstractmethod
    async def put(self, item: TItem, *, lock=True) -> None:
        """Add item to right-most position to buffer.

        Duplicates are supported.
        """

    @abstractmethod
    async def put_all(self, items: Sequence[TItem], *, lock=True) -> None:
        """Replace all items stored in buffer.

        Duplicates are supported.
        """

    @abstractmethod
    async def remove(self, item: TItem, *, lock=True) -> None:
        """Remove first occurrence of item from buffer or raise `ValueError` if not found."""

    @abstractmethod
    async def set_exception(self, exc: BaseException, *, lock=True) -> None:
        """Set exception that will be raised while trying to `.get()`/`.get_all()` item from \
        empty buffer."""

    def reset_exception(self) -> None:
        """Reset exception that was previously set by calling `.set_exception()`."""


class ComposableBuffer(Buffer[TItem]):
    """Utility class for composable/stackable buffer implementations to help with calling \
    underlying buffer."""

    def __init__(self, buffer: Buffer[TItem]):
        self._buffer = buffer

    @asynccontextmanager
    async def _handle_lock(self, lock: bool):
        if lock:
            async with self._buffer.condition:
                yield
        else:
            yield

    def size(self) -> int:
        return self._buffer.size()

    async def wait_for_any_items(self, *, lock=True) -> None:
        await self._buffer.wait_for_any_items(lock=lock)

    async def get(self, *, lock=True) -> TItem:
        return await self._buffer.get(lock=lock)

    async def get_all(self, *, lock=True) -> MutableSequence[TItem]:
        return await self._buffer.get_all(lock=lock)

    async def put(self, item: TItem, *, lock=True) -> None:
        await self._buffer.put(item, lock=lock)

    async def put_all(self, items: Sequence[TItem], *, lock=True) -> None:
        await self._buffer.put_all(items, lock=lock)

    async def remove(self, item: TItem, *, lock=True) -> None:
        await self._buffer.remove(item, lock=lock)

    async def set_exception(self, exc: BaseException, *, lock=True) -> None:
        await self._buffer.set_exception(exc, lock=lock)

    def reset_exception(self) -> None:
        self._buffer.reset_exception()


class SimpleBuffer(Buffer[TItem]):
    """Most basic implementation of Buffer interface."""

    def __init__(self, items: Optional[Sequence[TItem]] = None):
        self._items = list(items) if items is not None else []
        self._error: Optional[BaseException] = None

        self.condition = asyncio.Condition()

    def size(self) -> int:
        return len(self._items)

    @asynccontextmanager
    async def _handle_lock(self, lock: bool):
        if lock:
            async with self.condition:
                yield
        else:
            yield

    @trace_span()
    async def wait_for_any_items(self, lock=True) -> None:
        async with self._handle_lock(lock):
            await self.condition.wait_for(lambda: bool(self.size() or self._error))

    @trace_span()
    async def get(self, *, lock=True) -> TItem:
        async with self._handle_lock(lock):
            await self.wait_for_any_items(lock=False)

            if not self.size() and self._error:
                raise self._error

            return self._items.pop(0)

    async def get_all(self, *, lock=True) -> MutableSequence[TItem]:
        async with self._handle_lock(lock):
            if not self._items and self._error:
                raise self._error

            items = self._items[:]
            self._items.clear()

            return items

    async def put(self, item: TItem, *, lock=True) -> None:
        async with self._handle_lock(lock):
            self._items.append(item)
            self.condition.notify()

    async def put_all(self, items: Sequence[TItem], *, lock=True) -> None:
        async with self._handle_lock(lock):
            self._items.clear()
            self._items.extend(items[:])

            self.condition.notify(len(items))

    async def remove(self, item: TItem, *, lock=True) -> None:
        async with self._handle_lock(lock):
            self._items.remove(item)

    async def set_exception(self, exc: BaseException, *, lock=True) -> None:
        async with self._handle_lock(lock):
            self._error = exc
            self.condition.notify()

    def reset_exception(self) -> None:
        self._error = None


class ExpirableBuffer(ComposableBuffer[TItem]):
    """Composable `Buffer` that adds option to expire item after some time.

    Items that are already in provided buffer will not expire.
    """

    # TODO: Optimisation options: Use single expiration task that wakes up to expire the earliest
    #  item, then check next earliest item and sleep to it and repeat

    def __init__(
        self,
        buffer: Buffer[TItem],
        get_expiration_func: Callable[[TItem], MaybeAwaitable[Optional[timedelta]]],
        on_expired_func: Optional[Callable[[TItem], MaybeAwaitable[None]]] = None,
    ):
        super().__init__(buffer)

        self._get_expiration_func = get_expiration_func
        self._on_expired_func = on_expired_func

        # TODO: Could this collection be liable to race conditions?
        self._expiration_handlers: Dict[int, List[asyncio.TimerHandle]] = defaultdict(list)

    async def _add_expiration_task_for_item(self, item: TItem) -> None:
        expiration = await resolve_maybe_awaitable(self._get_expiration_func, item)

        if expiration is None:
            return

        loop = asyncio.get_event_loop()

        self._expiration_handlers[id(item)].append(
            loop.call_later(
                expiration.total_seconds(),
                lambda: create_task_with_logging(
                    self._expire_item(item), trace_id=get_trace_id_name(self, f"item-expire-{item}")
                ),
            )
        )

    def _remove_expiration_handler_for_item(self, item: TItem) -> None:
        item_id = id(item)

        if item_id not in self._expiration_handlers or not len(self._expiration_handlers[item_id]):
            return

        expiration_handle = self._expiration_handlers[item_id].pop(0)
        expiration_handle.cancel()

        if not self._expiration_handlers[item_id]:
            del self._expiration_handlers[item_id]

    def _remove_all_expiration_handlers(self) -> None:
        for handlers in self._expiration_handlers.values():
            for handler in handlers:
                handler.cancel()

        self._expiration_handlers.clear()

    async def get(self, *, lock=True) -> TItem:
        async with self._handle_lock(lock):
            item = await super().get(lock=False)

            self._remove_expiration_handler_for_item(item)

            return item

    async def get_all(self, *, lock=True) -> MutableSequence[TItem]:
        async with self._handle_lock(lock):
            items = await super().get_all(lock=False)

            self._remove_all_expiration_handlers()

            return items

    async def put(self, item: TItem, *, lock=True) -> None:
        async with self._handle_lock(lock):
            await super().put(item, lock=False)

            await self._add_expiration_task_for_item(item)

    async def put_all(self, items: Sequence[TItem], *, lock=True) -> None:
        async with self._handle_lock(lock):
            await super().put_all(items, lock=False)

            self._remove_all_expiration_handlers()

            await asyncio.gather(
                *[self._add_expiration_task_for_item(item) for item in items],
                return_exceptions=True,
            )

    async def remove(self, item: TItem, *, lock=True) -> None:
        async with self._handle_lock(lock):
            await super().remove(item, lock=False)

            self._remove_expiration_handler_for_item(item)

    @trace_span(show_arguments=True)
    async def _expire_item(self, item: TItem) -> None:
        await self.remove(item)

        if self._on_expired_func:
            await resolve_maybe_awaitable(self._on_expired_func, item)


class BackgroundFillBuffer(ComposableBuffer[TItem]):
    """Composable `Buffer` that adds option to fill buffer in background tasks.

    Background fill will happen only if background tasks are started by calling `.start()`
    and items were requested by `.request()`.
    """

    def __init__(
        self,
        buffer: Buffer[TItem],
        fill_func: Callable[[], Awaitable[TItem]],
        fill_concurrency_size=1,
        on_added_func: Optional[Callable[[TItem], Awaitable[None]]] = None,
    ):
        super().__init__(buffer)

        self._fill_func = fill_func
        self._fill_concurrency_size = fill_concurrency_size
        self._on_added_func = on_added_func

        self._is_started = False
        self._worker_tasks: List[asyncio.Task] = []
        self._workers_semaphore = SingleUseSemaphore()

    @trace_span()
    async def start(self) -> None:
        if self.is_started():
            raise RuntimeError("Already started!")

        for i in range(self._fill_concurrency_size):
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

    async def _worker_loop(self) -> None:
        while True:
            logger.debug("Waiting for fill item request...")

            async with self._workers_semaphore:
                logger.debug("Waiting for fill item request done")

                logger.debug("Adding new item...")

                item = await self._fill_func()

                await self.put(item)

            if self._on_added_func is not None:
                await self._on_added_func(item)

            logger.debug("Adding new item done with total of %d items in buffer", self.size())

    async def request(self, count: int) -> None:
        """Request given number of items to be filled in background."""

        await self._workers_semaphore.increase(count)

    def size_with_requested(self) -> int:
        """Return sum of item count stored in buffer and requested to be filled."""

        return self.size() + self._workers_semaphore.get_count_with_pending()

    async def get_all_requested(self, deadline: timedelta) -> MutableSequence[TItem]:
        """Await for all requested items with given deadline, then remove and return all items \
        stored in buffer."""

        if not self._workers_semaphore.finished.is_set():
            try:
                await asyncio.wait_for(
                    self._workers_semaphore.finished.wait(), deadline.total_seconds()
                )
            except asyncio.TimeoutError:
                pass

        return await self.get_all()
