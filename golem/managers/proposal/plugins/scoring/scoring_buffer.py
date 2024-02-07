import asyncio
import logging
from datetime import timedelta
from typing import Callable, Optional, Sequence

from golem.managers.base import ScorerWithOptionalWeight
from golem.managers.proposal.plugins.buffer import ProposalBuffer
from golem.managers.proposal.plugins.scoring import ProposalScoringMixin
from golem.resources import Proposal
from golem.utils.asyncio import (
    Buffer,
    ExpirableBuffer,
    SimpleBuffer,
    create_task_with_logging,
    ensure_cancelled,
)
from golem.utils.logging import get_trace_id_name, trace_span
from golem.utils.typing import MaybeAwaitable

logger = logging.getLogger(__name__)


class ProposalScoringBuffer(ProposalScoringMixin, ProposalBuffer):
    def __init__(
        self,
        min_size: int,
        max_size: int,
        fill_concurrency_size=1,
        fill_at_start=False,
        get_expiration_func: Optional[
            Callable[[Proposal], MaybeAwaitable[Optional[timedelta]]]
        ] = None,
        on_expiration_func: Optional[Callable[[Proposal], MaybeAwaitable[None]]] = None,
        scoring_debounce: timedelta = timedelta(seconds=10),
        proposal_scorers: Optional[Sequence[ScorerWithOptionalWeight]] = None,
    ) -> None:
        super().__init__(
            min_size=min_size,
            max_size=max_size,
            fill_concurrency_size=fill_concurrency_size,
            fill_at_start=fill_at_start,
            get_expiration_func=None,
            on_expiration_func=on_expiration_func,
            proposal_scorers=proposal_scorers,
        )

        self._scoring_debounce = scoring_debounce

        # Postponing argument would disable expiration from ProposalBuffer parent
        # as we want to expire only scored proposals instead
        self._get_expiration_func = get_expiration_func

        scored_buffer: Buffer[Proposal] = SimpleBuffer()

        if get_expiration_func is not None:
            scored_buffer = ExpirableBuffer(
                buffer=scored_buffer,
                get_expiration_func=get_expiration_func,
                on_expired_func=self._on_expired,
            )

        self._buffer_scored: Buffer[Proposal] = scored_buffer
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
            await ensure_cancelled(self._background_loop_task)
            self._background_loop_task = None

    async def _on_added(self, proposal: Proposal) -> None:
        pass  # explicit no-op

    async def _background_loop(self) -> None:
        while True:
            logger.debug(
                "Waiting for any proposals to score with debounce of `%s`...",
                self._scoring_debounce,
            )

            try:
                proposals = await self._buffer.get_requested(self._scoring_debounce)
            except Exception as e:
                await self._buffer_scored.set_exception(e)
                logger.debug(
                    "Encountered unexpected exception while getting proposal,"
                    " exception is set and background loop will be stopped!"
                )

                return

            logger.debug(
                "Waiting for any proposals done, %d new proposals will be scored", len(proposals)
            )

            proposals.extend(await self._buffer_scored.get_all())

            logger.debug("Scoring total %d proposals...", len(proposals))

            scored_proposals = await self.do_scoring(proposals)
            await self._buffer_scored.put_all([proposal for _, proposal in scored_proposals])

            logger.debug("Scoring total %d proposals done", len(proposals))

    async def _get_buffered_proposal(self) -> Proposal:
        return await self._buffer_scored.get()

    def _get_buffered_proposals_count(self) -> int:
        return super()._get_buffered_proposals_count() + self._buffer_scored.size()
