import logging

from golem.managers import ProposalManagerPlugin
from golem.resources import Proposal
from golem.utils.asyncio.buffer import BackgroundFillBuffer, SimpleBuffer
from golem.utils.logging import trace_span

logger = logging.getLogger(__name__)


class Buffer(ProposalManagerPlugin):
    def __init__(
        self,
        min_size: int,
        max_size: int,
        fill_concurrency_size=1,
        fill_at_start=False,
    ) -> None:
        self._min_size = min_size
        self._max_size = max_size
        self._fill_concurrency_size = fill_concurrency_size
        self._fill_at_start = fill_at_start

        self._buffer = BackgroundFillBuffer(
            buffer=SimpleBuffer(),
            fill_func=self._call_feed_func,
            fill_concurrency_size=self._fill_concurrency_size,
        )

    async def _call_feed_func(self) -> Proposal:
        return await self._get_proposal()

    @trace_span()
    async def start(self) -> None:
        await self._buffer.start()

        if self._fill_at_start:
            await self._request_items()

    @trace_span()
    async def stop(self) -> None:
        await self._buffer.stop()

    async def _request_items(self):
        count = self._max_size - self._buffer.size_with_requested()
        await self._buffer.request(count)

        logger.debug("Requested %s items", count)

    @trace_span(show_results=True)
    async def get_proposal(self) -> Proposal:
        if not self._get_items_count():
            logger.debug("No items to get, requesting fill")
            await self._request_items()

        proposal = await self._get_item()

        items_count = self._get_items_count()
        if items_count < self._min_size:
            logger.debug(
                "Target items count `%s` is below min size `%d`, requesting fill",
                items_count,
                self._min_size,
            )
            await self._request_items()
        else:
            logger.debug(
                "Target items count `%s` is not below min size `%d`, requesting fill not needed",
                items_count,
                self._min_size,
            )

        return proposal

    async def _get_item(self) -> Proposal:
        return await self._buffer.get()

    def _get_items_count(self) -> int:
        return self._buffer.size_with_requested()
