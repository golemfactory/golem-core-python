import asyncio
from typing import AsyncIterator, Awaitable, Optional
from golem_api.low.market import Agreement
from golem_api.low.activity import Activity


class ActivityCreator():
    async def __call__(self, in_stream: AsyncIterator[Awaitable[Agreement]]) -> AsyncIterator[Awaitable[Activity]]:
        while True:
            yield asyncio.create_task(self._process_next(in_stream))

    async def _process_next(self, in_stream: AsyncIterator[Awaitable[Agreement]]) -> Activity:
        while True:
            try:
                in_val = await in_stream.__anext__()
                break
            except RuntimeError:
                await asyncio.sleep(0.01)
        return await self._process_single_item(in_val)

    async def _process_single_item(self, agreement_task: Awaitable[Agreement]) -> Optional[Activity]:
        try:
            agreement = await agreement_task
            return await agreement.create_activity()
        except Exception as e:
            print(e)
            return None
