import asyncio
import logging
from abc import abstractmethod, ABC
from collections import defaultdict
from datetime import timedelta
from typing import TypeVar, Generic, Optional, Sequence, Iterable, Callable, List, Dict, Awaitable, MutableSequence

from golem.utils.asyncio import create_task_with_logging, cancel_and_await_many, cancel_and_await
from golem.utils.logging import trace_span, get_trace_id_name
from golem.utils.semaphore import SingleUseSemaphore

TItem = TypeVar("TItem")
TBuffer = TypeVar("TBuffer")

logger = logging.getLogger(__name__)


class Buffer(ABC, Generic[TItem]):
    @abstractmethod
    def size(self) -> int:
        ...

    @abstractmethod
    async def wait_for_any_items(self) -> None:
        ...

    @abstractmethod
    async def get(self) -> TItem:
        ...

    @abstractmethod
    async def get_all(self) -> MutableSequence[TItem]:
        ...

    @abstractmethod
    async def put(self, item: TItem) -> None:
        ...

    @abstractmethod
    async def put_all(self, items: Sequence[TItem]) -> None:
        ...

    @abstractmethod
    async def remove(self, item: TItem) -> None:
        ...


class ComposableBuffer(Generic[TBuffer, TItem], Buffer[TItem]):
    def __init__(self, buffer: TBuffer):
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
    def __init__(self, items: Optional[Sequence[TItem]] = None):
        self._items = list(items) if items is not None else []

        self._have_items = asyncio.Event()  # TODO: collections of future-object waiters instead of event?

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


class ExpirableBuffer(ComposableBuffer[Buffer, TItem]):
    # Optimisation options: Use single expiration task that wakes up to expire the earliest item,
    # then check next earliest item and sleep to it and repeat
    def __init__(self, buffer: Buffer, get_expiration_func: Callable[[TItem], Optional[timedelta]]):
        super().__init__(buffer)

        self._get_expiration_func = get_expiration_func

        self._lock = asyncio.Lock()
        self._expiration_tasks: Dict[int, List[asyncio.Task]] = defaultdict(list)

    def _add_expiration_task_for_item(self, item: TItem) -> None:
        expiration = self._get_expiration_func(item)

        if expiration is None:
            return

        self._expiration_tasks[id(item)].append(asyncio.create_task(self._expire_item(expiration, item)))

    async def _remove_expiration_task_for_item(self, item: TItem) -> None:
        item_id = id(item)

        if item_id not in self._expiration_tasks or not len(self._expiration_tasks[item_id]):
            return

        expiration_task = self._expiration_tasks[item_id].pop(0)

        await cancel_and_await(expiration_task)

        if not self._expiration_tasks[item_id]:
            del self._expiration_tasks[item_id]

    async def _remove_all_expiration_tasks(self) -> None:
        await cancel_and_await_many(self._expiration_tasks)
        self._expiration_tasks.clear()

    async def get(self) -> Iterable[TItem]:
        async with self._lock:
            item = await super().get()
            await self._remove_expiration_task_for_item(item)

            return item

    async def get_all(self) -> MutableSequence[TItem]:
        async with self._lock:
            items = await super().get_all()
            await self._remove_all_expiration_tasks()
            return items

    async def put(self, item: TItem) -> None:
        async with self._lock:
            await super().put(item)
            self._add_expiration_task_for_item(item)

    async def put_all(self, items: Sequence[TItem]) -> None:
        async with self._lock:
            await super().put_all(items)
            await self._remove_all_expiration_tasks()

            for item in items:
                self._add_expiration_task_for_item(item)

    async def remove(self, item: TItem) -> None:
        async with self._lock:
            await super().remove(item)
            await self._remove_expiration_task_for_item(item)

    async def _expire_item(self, expiration: timedelta, item: TItem) -> None:
        await asyncio.sleep(expiration.total_seconds())

        await self.remove(item)


class BackgroundFeedBuffer(ComposableBuffer[Buffer, TItem]):
    def __init__(
        self,
        buffer: Buffer,
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
        await self._workers_semaphore.increase(count)

    @property
    def finished(self):
        return self._workers_semaphore.finished


class BatchedGetAllBuffer(ComposableBuffer[BackgroundFeedBuffer, TItem]):
    def __init__(self, buffer: BackgroundFeedBuffer, batch_deadline: timedelta):
        super().__init__(buffer)

        self._batch_deadline = batch_deadline

        self._lock = asyncio.Lock()

    async def get_all(self) -> Sequence[TItem]:
        async with self._lock:
            await self.wait_for_any_items()

            try:
                await asyncio.wait_for(self._buffer.finished.wait(), self._batch_deadline.total_seconds())
            except TimeoutError:
                pass

            return await super().get_all()
