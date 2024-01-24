import asyncio
import logging
from datetime import timedelta
from typing import Optional

from golem.managers.proposal.plugins.buffer import BufferPlugin as BufferPlugin
from golem.managers.proposal.plugins.scoring import ProposalScoringMixin
from golem.resources import Proposal
from golem.utils.asyncio import Buffer, SimpleBuffer, cancel_and_await, create_task_with_logging
from golem.utils.logging import get_trace_id_name, trace_span

logger = logging.getLogger(__name__)


class ScoringBufferPlugin(ProposalScoringMixin, BufferPlugin):
    def __init__(self, update_interval: timedelta = timedelta(seconds=10), *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._update_interval = update_interval

        self._buffer_scored: Buffer[Proposal] = SimpleBuffer()
        self._background_loop_task: Optional[asyncio.Task] = None

    @trace_span()
    async def start(self) -> None:
        await super().start()

        self._background_loop_task = create_task_with_logging(
            self._background_loop(), trace_id=get_trace_id_name(self, "background-loop")
        )

    @trace_span()
    async def stop(self) -> None:
        await super().stop()

        if self._background_loop_task is not None:
            await cancel_and_await(self._background_loop_task)
            self._background_loop_task = None

    async def _on_added_callback(self):
        pass  # explicit no-op

    async def _background_loop(self) -> None:
        while True:
            logger.debug("Waiting for any items to score...")
            await self._buffer.wait_for_any_items()
            logger.debug("Waiting for any items to score done, items are available for scoring")

            logger.debug("Waiting for more items up to %s...", self._update_interval)
            items = await self._buffer.get_all_requested(self._update_interval)
            logger.debug("Waiting for more items done, %d new items will be scored", len(items))

            items.extend(await self._buffer_scored.get_all())

            logger.debug("Scoring total %d items...", len(items))

            scored_items = await self.do_scoring(items)
            await self._buffer_scored.put_all([proposal for _, proposal in scored_items])

            logger.debug("Scoring total %d items done", len(items))

    async def _get_item(self) -> Proposal:
        return await self._buffer_scored.get()

    def _get_items_count(self) -> int:
        return super()._get_items_count() + self._buffer_scored.size()
