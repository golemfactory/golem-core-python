from golem.managers import ProposalManagerPlugin
from golem.resources import Proposal
from golem.utils.asyncio.buffer import BackgroundFeedBuffer, SimpleBuffer


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

        self._buffer = BackgroundFeedBuffer(
            buffer=SimpleBuffer(),
            feed_func=self._call_feed_func,
            feed_concurrency_size=self._fill_concurrency_size,
        )

    async def _call_feed_func(self) -> Proposal:
        return await self._get_proposal()

    async def start(self) -> None:
        await self._buffer.start()

        if self._fill_at_start:
            await self._request_items()

    async def stop(self) -> None:
        await self._buffer.stop()

    async def _request_items(self):
        await self._buffer.request(self._max_size - self._buffer.size_with_requested())

    async def get_proposal(self) -> Proposal:
        if not self._get_items_count():
            await self._request_items()

        proposal = await self._get_item()

        if self._get_items_count() < self._min_size:
            await self._request_items()

        return proposal

    async def _get_item(self) -> Proposal:
        return await self._buffer.get()

    def _get_items_count(self) -> int:
        return self._buffer.size_with_requested()
