import asyncio
import logging
from typing import Optional

from golem.managers.proposal.plugins.buffer import Buffer
from golem.utils.asyncio import create_task_with_logging
from golem.utils.logging import trace_span

logger = logging.getLogger(__name__)


class Score(Buffer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._scored = []
        self._scored_condition = asyncio.Condition()
        self._background_loop_task: Optional[asyncio.Task] = None

    @trace_span()
    async def start(self) -> None:
        await super().start()

        self._background_loop_task = create_task_with_logging(self._background_loop())

    @trace_span()
    async def stop(self) -> None:
        await super().stop()

        if self._background_loop_task is not None:
            self._background_loop_task.cancel()
            self._background_loop_task = None

    def is_started(self) -> bool:
        is_started = super().is_started()
        return (
            is_started
            and self._background_loop_task is not None
            and not self._background_loop_task.done()
        )

    async def _background_loop(self):
        while True:
            await asyncio.sleep(10)
            # logger.debug("Waiting for any item requests...")
            # await self._items_requests_pending_event.wait()
            #
            # timeout = (
            #     None if self._update_interval is None else self._update_interval.total_seconds()
            # )
            # logger.debug("Some items were requested, waitng on all with timeout `%s`", timeout)
            #
            # try:
            #     await asyncio.wait_for(self._items_requests_ready_event.wait(), timeout=timeout)
            #     self._items_requests_ready_event.clear()
            #     logger.debug("Got all requested items")
            # except asyncio.TimeoutError:
            #     logger.debug("Waiting for all requested items timed out, updating anyways...")
            #
            # async with self._buffered_condition:
            #     items_to_score = self._buffered[:]
            #     self._buffered.clear()
            #
            # async with self._scored_condition:
            #     all_items = self._scored + items_to_score
            #
            #     self._do_scoring()
            #
            #     logger.debug(f"Item collection updated {self._scored}")
            #
            #     self._scored_condition.notify_all()

    async def _get_item(self):
        async with self._scored_condition:
            if self._get_items_count() == 0:  # This supports lazy (not at start) buffer filling
                logger.debug("No items to get, requesting fill")
                self._handle_item_requests()

            logger.debug("Waiting for any item to pick...")

            await self._scored_condition.wait_for(lambda: 0 < len(self._scored))
            item = self._scored.pop()

            # Check if we need to request any additional items
            if self._get_items_count() < self._min_size:
                self._handle_item_requests()

            return item

    def _get_items_count(self):
        items_count = super()._get_items_count()

        return items_count + len(self._scored)
