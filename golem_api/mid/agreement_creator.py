import asyncio
from typing import AsyncIterator, Awaitable, Optional

from golem_api.low.market import Agreement, Proposal


class AgreementCreator():
    async def __call__(self, in_stream: AsyncIterator[Awaitable[Proposal]]) -> AsyncIterator[Awaitable[Agreement]]:
        while True:
            yield asyncio.create_task(self._process_next(in_stream))

    async def _process_next(self, in_stream: AsyncIterator[Awaitable[Proposal]]) -> Proposal:
        while True:
            try:
                in_val = await in_stream.__anext__()
                break
            except RuntimeError:
                await asyncio.sleep(0.01)
        return await self._process_single_item(in_val)

    async def _process_single_item(self, proposal_task: Awaitable[Proposal]) -> Optional[Agreement]:
        proposal = await proposal_task
        agreement = await proposal.create_agreement()
        await agreement.confirm()

        approved = await agreement.wait_for_approval()
        if approved:
            return agreement
        return None
