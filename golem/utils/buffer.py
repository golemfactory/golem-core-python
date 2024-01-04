import asyncio
import logging
from abc import abstractmethod, ABC
from collections import defaultdict
from datetime import timedelta
from typing import TypeVar, Generic, Optional, Sequence, Iterable, Callable, List, Dict, Awaitable

from golem.utils.asyncio import create_task_with_logging, cancel_and_await_many
from golem.utils.counter import AsyncCounter
from golem.utils.logging import trace_span, get_trace_id_name

TItem = TypeVar("TItem")

logger = logging.getLogger(__name__)


class Buffer(ABC, Generic[TItem]):
    @abstractmethod
    async def get(self) -> TItem:
        ...

    @abstractmethod
    async def put(self, item: TItem, *, notify_all=True) -> None:
        ...

    @abstractmethod
    async def remove(self, item: TItem) -> None:
        ...

    @abstractmethod
    def size(self) -> int:
        ...

    @abstractmethod
    async def notify_all(self) -> None:
        ...


class ComposableBuffer(Generic[TItem], Buffer[TItem]):
    def __init__(self, buffer: Buffer):
        self._buffer = buffer

    async def get(self) -> TItem:
        return await self._buffer.get()

    async def put(self, item: TItem, *, notify_all=True) -> None:
        await self._buffer.put(item, notify_all=notify_all)

    async def remove(self, item: TItem) -> None:
        await self._buffer.remove(item)

    def size(self) -> int:
        return self._buffer.size()

    async def notify_all(self) -> None:
        await self._buffer.notify_all()


class SimpleBuffer(Buffer[TItem]):
    def __init__(self, items: Optional[Sequence[TItem]] = None):
        self._items = list(items) if items is not None else []

        self._condition = asyncio.Condition()

    async def get(self) -> TItem:
        async with self._condition:
            await self._condition.wait_for(lambda: 0 < len(self._items))
            return self._items.pop(0)

    async def put(self, item: TItem, *, notify_all=True) -> None:
        async with self._condition:
            self._items.append(item)

            if notify_all:
                self._condition.notify_all()

    async def remove(self, item: TItem) -> None:
        async with self._condition:
            self._items.remove(item)

    def size(self) -> int:
        return len(self._items)

    async def notify_all(self) -> None:
        async with self._condition:
            self._condition.notify_all()


class ExpirableBuffer(ComposableBuffer[TItem]):
    # Optimisation options: Use single expiration task that wakes up to expire the earliest item,
    # then check next earliest item and sleep to it and repeat
    def __init__(self, buffer: Buffer, get_expiration_func: Callable[[TItem], Optional[timedelta]]):
        super().__init__(buffer)

        self._get_expiration_func = get_expiration_func

        self._lock = asyncio.Lock()
        self._expiration_tasks: Dict[int, List[asyncio.Task]] = defaultdict(list)

    def _cancel_expiration_task_for_item(self, item: TItem) -> None:
        item_id = id(item)

        if item_id not in self._expiration_tasks or not len(self._expiration_tasks[item_id]):
            return

        self._expiration_tasks[item_id].pop(0)

        if not self._expiration_tasks[item_id]:
            del self._expiration_tasks[item_id]

    async def get(self) -> Iterable[TItem]:
        async with self._lock:
            item = await self._buffer.get()
            self._cancel_expiration_task_for_item(item)

            return item

    async def put(self, item: TItem, *, notify_all=True) -> None:
        async with self._lock:
            await self._buffer.put(item, notify_all=False)
            expiration = self._get_expiration_func(item)

            if expiration is not None:
                self._expiration_tasks[id(item)].append(asyncio.create_task(self._expire_item(expiration, item)))

            if notify_all:
                await self._buffer.notify_all()

    async def remove(self, item: TItem) -> None:
        async with self._lock:
            await self._buffer.remove(item)
            self._cancel_expiration_task_for_item(item)

    async def _expire_item(self, expiration: timedelta, item: TItem) -> None:
        await asyncio.sleep(expiration.total_seconds())

        async with self._lock:
            await self._buffer.remove(item)
            del self._expiration_tasks[id(item)]

    async def notify_all(self) -> None:
        async with self._lock:
            await self._buffer.notify_all()


class BackgroundFedBuffer(ComposableBuffer[TItem]):
    def __init__(
        self,
        buffer: Buffer,
        feed_func: Callable[[], Awaitable[TItem]],
        min_size: int,
        max_size: int,
        fill_concurrency_size: int = 1,
        fill_at_start=False,
    ):
        super().__init__(buffer)

        self._feed_func = feed_func
        self._min_size = min_size
        self._max_size = max_size
        self._fill_concurrency_size = fill_concurrency_size
        self._fill_at_start = fill_at_start

        self._is_started = False
        self._worker_tasks: List[asyncio.Task] = []
        self._requests_counter = AsyncCounter()
        self._lock = asyncio.Lock()

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

        if self._fill_at_start:
            await self._handle_item_requests()

        self._is_started = True

    @trace_span()
    async def stop(self) -> None:
        if not self.is_started():
            raise RuntimeError("Already stopped!")

        await cancel_and_await_many(self._worker_tasks)
        self._worker_tasks.clear()
        self._is_started = False

        self._requests_counter = AsyncCounter()

    def is_started(self) -> bool:
        return self._is_started

    async def _worker_loop(self):
        while True:
            await self._requests_counter.decrement()

            item = await self._feed_func()

            await self._buffer.put(item)

            self._requests_counter.task_done()

    async def get(self) -> TItem:
        async with self._lock:
            if self._size_with_pending() == 0:  # This supports lazy (not at start) buffer filling
                logger.debug("No items to get, requesting fill")
                await self._handle_item_requests()

            logger.debug("Waiting for any item to pick...")

            item = await self._buffer.get()

            # Check if we need to request any additional items
            if self._size_with_pending() < self._min_size:
                await self._handle_item_requests()

            return item

    def _size_with_pending(self):
        return self._buffer.size() + self._requests_counter.pending_count()

    @trace_span()
    async def _handle_item_requests(self) -> None:
        items_to_request = self._max_size - self._size_with_pending()

        await self._requests_counter.increment(items_to_request)

        logger.debug("Requested %d items", items_to_request)
