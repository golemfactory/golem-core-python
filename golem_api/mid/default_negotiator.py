import asyncio
from typing import AsyncIterator, Awaitable, Optional

from golem_api.low.market import Proposal


class DefaultNegotiator():
    async def __call__(self, in_stream: AsyncIterator[Proposal]) -> AsyncIterator[Awaitable[Proposal]]:
        while True:
            yield asyncio.create_task(self._process_next(in_stream))

    async def _process_next(self, in_stream: AsyncIterator[Proposal]) -> Proposal:
        while True:
            try:
                in_val = await in_stream.__anext__()
                break
            except RuntimeError:
                await asyncio.sleep(0.01)
        return await self._process_single_item(in_val)

    async def _process_single_item(self, proposal: Proposal) -> Optional[Proposal]:
        our_response = await proposal.respond()
        async for their_response in our_response.responses():
            return their_response
        return None
