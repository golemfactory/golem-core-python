import asyncio
import logging
from datetime import timedelta
from typing import List, Optional

from golem.managers.proposal.plugins.buffer import Buffer
from golem.managers.proposal.plugins.scoring.mixins import ProposalScoringMixin
from golem.resources import Proposal
from golem.utils.asyncio import create_task_with_logging
from golem.utils.logging import get_trace_id_name, trace_span

logger = logging.getLogger(__name__)


class ScoringBuffer(ProposalScoringMixin, Buffer):
    def __init__(
        self,
        update_interval: timedelta = timedelta(seconds=10),
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self._scored: List[Proposal] = []
        self._scored_condition = asyncio.Condition()
        self._background_loop_task: Optional[asyncio.Task] = None

        self._items_requested_event = asyncio.Event()
        self._update_interval = update_interval

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
        # TODO: Rework this flow to:
        #  - Use composition instead of inheritance
        #  - Get rid of loop checking state for proper state
        #     - composable Buffer should expose async context that exposes its items
        #       and items asyncio.Condition

        while True:
            logger.debug("Waiting for any requested items...")
            await self._items_requested_event.wait()
            logger.debug("Waiting for any requested items done")

            keep_retrying = True
            while keep_retrying:  # FIXME: Needs refactor too
                logger.debug("Waiting up to %s for all requested items...", self._update_interval)
                try:
                    await asyncio.wait_for(
                        self._requests_queue.join(),
                        timeout=self._update_interval.total_seconds(),
                    )
                except asyncio.TimeoutError:
                    logger.debug(
                        "Waiting up to %s for all requested items failed with timeout, trying to"
                        "update anyways...",
                        self._update_interval,
                    )
                else:
                    logger.debug(
                        "Waiting up to %s for all requested items done", self._update_interval
                    )
                    keep_retrying = False
                    self._items_requested_event.clear()

                async with self._buffered_condition:
                    if not self._buffered:
                        logger.debug("Update not needed, as no items were buffered in the meantime")
                        continue

                    items_to_score = self._buffered[:]
                    self._buffered.clear()

                async with self._scored_condition:
                    scored_proposals = await self.do_scoring(self._scored + items_to_score)
                    self._scored = [proposal for _, proposal in scored_proposals]

                    logger.debug("Item collection updated %s", scored_proposals)

                    self._scored_condition.notify_all()

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

    def _handle_item_requests(self) -> None:
        super()._handle_item_requests()

        self._items_requested_event.set()

    def _get_items_count(self):
        items_count = super()._get_items_count()

        return items_count + len(self._scored)
