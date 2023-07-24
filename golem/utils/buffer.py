import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import timedelta
from typing import Awaitable, Callable, Generic, List, MutableSequence, Optional, Sequence, TypeVar

from golem.utils.asyncio import create_task_with_logging
from golem.utils.logging import trace_span

TItem = TypeVar("TItem")

logger = logging.getLogger(__name__)


class Buffer(ABC, Generic[TItem]):
    @abstractmethod
    async def get_item(self) -> TItem:
        ...

    @abstractmethod
    async def start(self, *, fill=False) -> None:
        ...

    @abstractmethod
    async def stop(self) -> None:
        ...


async def default_update_callback(
    items: MutableSequence[TItem], items_to_process: Sequence[TItem]
) -> None:
    items.extend(items_to_process)


class ConcurrentlyFilledBuffer(Buffer[TItem], Generic[TItem]):
    def __init__(
        self,
        fill_callback: Callable[[], Awaitable[TItem]],
        min_size: int,
        max_size: int,
        update_callback: Callable[
            [MutableSequence[TItem], Sequence[TItem]], Awaitable[None]
        ] = default_update_callback,
        update_interval: Optional[timedelta] = None,
    ):
        self._fill_callback = fill_callback
        self._min_size = min_size
        self._max_size = max_size
        self._update_callback = update_callback
        self._update_interval = update_interval

        self._items_to_process: List[TItem] = []
        self._items_to_process_lock = asyncio.Lock()
        self._items: List[TItem] = []
        self._items_condition = asyncio.Condition()
        self._items_requested_tasks: List[asyncio.Task] = []
        self._items_requests_pending_event = asyncio.Event()
        self._items_requests_ready_event = asyncio.Event()

        self._background_loop_task: Optional[asyncio.Task] = None

    @trace_span()
    async def start(self, *, fill=False) -> None:
        if self.is_started():
            raise RuntimeError("Already started!")

        self._background_loop_task = create_task_with_logging(self._background_loop())

        if fill:
            self._handle_item_requests()

    @trace_span()
    async def stop(self) -> None:
        if not self.is_started():
            raise RuntimeError("Already stopped!")

        if self._background_loop_task is not None:
            self._background_loop_task.cancel()

            try:
                await self._background_loop_task
            except asyncio.CancelledError:
                pass

            self._background_loop_task = None

        tasks_to_cancel = self._items_requested_tasks[:]
        for task in tasks_to_cancel:
            task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

    def is_started(self) -> bool:
        return self._background_loop_task is not None and not self._background_loop_task.done()

    @trace_span(show_results=True)
    async def get_item(self) -> TItem:
        if not self.is_started():
            raise RuntimeError("Not started!")

        async with self._items_condition:
            if not self._items:
                logger.debug("No items to get, requesting fill")
                self._handle_item_requests()

            logger.debug("Waiting for any item to pick...")

            def check():
                logger.debug("check %s", len(self._items))
                return 0 < len(self._items)

            await self._items_condition.wait_for(check)

            item = self._items.pop(0)

        self._handle_item_requests()

        return item

    @trace_span()
    def _handle_item_requests(self) -> None:
        # Check if we need to request any additional items
        items_len = len(self._items)
        if self._min_size <= items_len:
            logger.debug(
                "Items count `%d` are not below min_size `%d`, skipping", items_len, self._min_size
            )
            return

        items_to_request = self._max_size - items_len - len(self._items_requested_tasks)

        self._items_requests_pending_event.set()

        def on_completion(task):
            self._items_requested_tasks.remove(task)

            if not self._items_requested_tasks:
                logger.debug("All requested items received")
                self._items_requests_pending_event.clear()
                self._items_requests_ready_event.set()

        for _ in range(items_to_request):
            task = create_task_with_logging(self._fill())
            task.add_done_callback(on_completion)
            self._items_requested_tasks.append(task)

        logger.debug("Requested %d items", items_to_request)

    async def _background_loop(self) -> None:
        while True:
            logger.debug("Waiting for any item requests...")
            await self._items_requests_pending_event.wait()

            timeout = (
                None if self._update_interval is None else self._update_interval.total_seconds()
            )
            logger.debug("Some items were requested, waitng on all with timeout `%s`", timeout)

            try:
                await asyncio.wait_for(self._items_requests_ready_event.wait(), timeout=timeout)
                self._items_requests_ready_event.clear()
                logger.debug("Got all requested items")
            except asyncio.TimeoutError:
                logger.debug("Waiting for all requested items timed out, updating anyways...")

            async with self._items_to_process_lock:
                items_to_process = self._items_to_process[:]
                self._items_to_process.clear()

            async with self._items_condition:
                await self._update_callback(self._items, items_to_process)

                logger.debug(f"Item collection updated {self._items}")

                self._items_condition.notify_all()

    async def _fill(self):
        item = await self._fill_callback()

        logger.debug("Requested item `%s` received", item)

        async with self._items_to_process_lock:
            self._items_to_process.append(item)
