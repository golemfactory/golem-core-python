import asyncio
import logging
from asyncio import Queue
from typing import List

from golem.managers import ProposalManagerPlugin
from golem.resources import Proposal
from golem.utils.asyncio import create_task_with_logging
from golem.utils.logging import get_trace_id_name, trace_span

logger = logging.getLogger(__name__)


class Buffer(ProposalManagerPlugin):
    def __init__(
        self,
        min_size: int,
        max_size: int,
        fill_concurrency_size: int = 1,
        fill_at_start=False,
    ):
        self._min_size = min_size
        self._max_size = max_size
        self._fill_concurrency_size = fill_concurrency_size
        self._fill_at_start = fill_at_start

        self._get_proposal_lock = asyncio.Lock()
        self._worker_tasks: List[asyncio.Task] = []
        # As there is no awaitable counter, queue with dummy values is used
        self._requests_queue: Queue[int] = asyncio.Queue()
        self._requests_pending_count = 0
        self._buffered: List[Proposal] = []
        self._buffered_condition = asyncio.Condition()
        self._is_started = False

    @trace_span(show_results=True)
    async def get_proposal(self) -> Proposal:
        if not self.is_started():
            raise RuntimeError("Not started!")

        async with self._get_proposal_lock:
            return await self._get_item()

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
            self._handle_item_requests()

        self._is_started = True

    @trace_span()
    async def stop(self) -> None:
        if not self.is_started():
            raise RuntimeError("Already stopped!")

        for worker_task in self._worker_tasks:
            worker_task.cancel()

            try:
                await worker_task
            except asyncio.CancelledError:
                pass

        self._worker_tasks.clear()
        self._is_started = False

        self._requests_queue = asyncio.Queue()
        self._requests_pending_count = 0

    def is_started(self) -> bool:
        return self._is_started

    async def _worker_loop(self):
        while True:
            await self._wait_for_any_item_requests()

            item = await self._get_proposal()

            async with self._buffered_condition:
                self._buffered.append(item)

                self._buffered_condition.notify_all()

            self._requests_queue.task_done()
            self._requests_pending_count -= 1

    @trace_span()
    async def _wait_for_any_item_requests(self) -> None:
        await self._requests_queue.get()

    async def _get_item(self):
        async with self._buffered_condition:
            if self._get_items_count() == 0:  # This supports lazy (not at start) buffer filling
                logger.debug("No items to get, requesting fill")
                self._handle_item_requests()

            logger.debug("Waiting for any item to pick...")

            await self._buffered_condition.wait_for(lambda: 0 < len(self._buffered))
            item = self._buffered.pop()

            # Check if we need to request any additional items
            if self._get_items_count() < self._min_size:
                self._handle_item_requests()

            return item

    def _get_items_count(self):
        return len(self._buffered) + self._requests_pending_count

    @trace_span()
    def _handle_item_requests(self) -> None:
        items_to_request = self._max_size - self._get_items_count()

        for i in range(items_to_request):
            self._requests_queue.put_nowait(i)

        self._requests_pending_count += items_to_request

        logger.debug("Requested %d items", items_to_request)
