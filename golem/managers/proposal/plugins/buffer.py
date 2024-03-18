import json
import logging
import re
from datetime import timedelta
from typing import Callable, Optional

from ya_market import ApiException

from golem.managers import ProposalManagerPlugin
from golem.resources import Proposal
from golem.utils.asyncio.buffer import BackgroundFillBuffer, Buffer, ExpirableBuffer, SimpleBuffer
from golem.utils.asyncio.tasks import resolve_maybe_awaitable
from golem.utils.logging import trace_span
from golem.utils.typing import MaybeAwaitable

logger = logging.getLogger(__name__)


class ProposalBuffer(ProposalManagerPlugin):
    def __init__(
        self,
        min_size: int,
        max_size: int,
        fill_concurrency_size: int = 1,
        fill_at_start=False,
        get_expiration_func: Optional[
            Callable[[Proposal], MaybeAwaitable[Optional[timedelta]]]
        ] = None,
        on_expiration_func: Optional[Callable[[Proposal], MaybeAwaitable[None]]] = None,
    ) -> None:
        self._min_size = min_size
        self._max_size = max_size
        self._fill_concurrency_size = fill_concurrency_size
        self._fill_at_start = fill_at_start
        self._get_expiration_func = get_expiration_func
        self._on_expiration_func = on_expiration_func

        # TODO: Consider moving buffer composition from here to plugin level
        buffer: Buffer[Proposal] = SimpleBuffer()

        if self._get_expiration_func:
            buffer = ExpirableBuffer(
                buffer=buffer,
                get_expiration_func=self._get_expiration_func,
                on_expired_func=self._on_expired,
            )

        self._buffer: BackgroundFillBuffer[Proposal] = BackgroundFillBuffer(
            buffer=buffer,
            fill_func=self._call_feed_func,
            fill_concurrency_size=self._fill_concurrency_size,
            on_added_func=self._on_added,
        )

    async def _call_feed_func(self) -> Proposal:
        return await self._get_proposal()

    async def _on_added(self, proposal: Proposal) -> None:
        count_current = self._buffer.size()
        count_with_requested = self._buffer.size_with_requested()
        pending = count_with_requested - count_current

        logger.debug(
            "Proposal added, having %d proposals, and %d already requested, target %d",
            count_current,
            pending,
            self._max_size,
        )

    async def _on_expired(self, proposal: Proposal):
        logger.debug("Rejecting expired `%r` and requesting fill", proposal)

        try:
            await proposal.reject("Proposal no longer needed due to its near expiration.")
        except ApiException as e:
            message = json.loads(e.body)["message"]
            if e.status == 400 and re.match(
                r"^Subscription \[([^]]+)\] (wasn't found|expired).$", message
            ):
                logger.warning(
                    "Proposal assumed already expired. Consider shortening the expiry duration."
                )
            else:
                raise

        await self._request_proposals()

        if self._on_expiration_func:
            await resolve_maybe_awaitable(self._on_expiration_func(proposal))

    @trace_span()
    async def start(self) -> None:
        await self._buffer.start()

        if self._fill_at_start:
            await self._request_proposals()

    @trace_span()
    async def stop(self) -> None:
        await self._buffer.stop()

    async def _request_proposals(self) -> None:
        count_current = self._buffer.size()
        count_with_requested = self._buffer.size_with_requested()
        requested = self._max_size - count_with_requested

        logger.debug(
            "Proposal count %d and %d already requested, requesting additional %d to match"
            " target %d",
            count_current,
            count_with_requested - count_current,
            requested,
            self._max_size,
        )

        await self._buffer.request(requested)

    @trace_span(show_results=True)
    async def get_proposal(self) -> Proposal:
        if not self._get_buffered_proposals_count():
            logger.debug("No proposals to get, requesting fill")
            await self._request_proposals()

        proposal = await self._get_buffered_proposal()

        proposals_count = self._get_buffered_proposals_count()
        if proposals_count < self._min_size:
            logger.debug(
                "Proposals count %d is below minimum size %d, requesting fill",
                proposals_count,
                self._min_size,
            )
            await self._request_proposals()
        else:
            logger.debug(
                "Proposals count %d is above minimum size %d, skipping fill",
                proposals_count,
                self._min_size,
            )

        return proposal

    async def _get_buffered_proposal(self) -> Proposal:
        return await self._buffer.get()

    def _get_buffered_proposals_count(self) -> int:
        return self._buffer.size()
