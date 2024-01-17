import asyncio
from datetime import timedelta

from golem.managers import ProposalScoringMixin
from golem.managers.proposal.plugins.new_buffer import Buffer as BufferPlugin
from golem.resources import Proposal
from golem.utils.buffer import Buffer


class ScoringBuffer(ProposalScoringMixin, BufferPlugin):
    def __init__(self, update_interval: timedelta = timedelta(seconds=10), *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._update_interval = update_interval

        self._buffer_scored: Buffer[Proposal] = Buffer()
        self._lock = asyncio.Lock()

    async def _background_loop(self) -> None:
        while True:
            self._buffer.wait_for_any_items()

            async with self._lock:
                items = await self._buffer.get_all_requested(self._update_interval)
                items.extend(await self._buffer_scored.get_all())
                scored_items = await self.do_scoring(items)
                await self._buffer_scored.put_all([proposal for _, proposal in scored_items])

    async def _get_item(self) -> Proposal:
        async with self._lock:
            return await self._buffer_scored.get()

    def _get_items_count(self) -> int:
        return super()._get_items_count() + self._buffer_scored.size()
