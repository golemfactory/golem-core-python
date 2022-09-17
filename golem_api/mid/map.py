import asyncio
from typing import AsyncIterator, Awaitable, Optional, TypeVar, Callable


InType = TypeVar("InType")
OutType = TypeVar("OutType")


class Map:
    def __init__(self, func: Callable[[Awaitable[InType]], Awaitable[OutType]]):
        self.func = func

    async def __call__(self, in_stream: AsyncIterator[Awaitable[InType]]) -> AsyncIterator[Awaitable[OutType]]:
        while True:
            yield asyncio.create_task(self._process_next(in_stream))

    async def _process_next(self, in_stream: AsyncIterator[Awaitable[InType]]) -> OutType:
        while True:
            try:
                in_val = await in_stream.__anext__()
                break
            except RuntimeError:
                await asyncio.sleep(0.01)
        return await self._process_single_item(in_val)

    async def _process_single_item(self, in_task: Awaitable[InType]) -> Optional[Awaitable[OutType]]:
        try:
            in_ = await in_task
            return await self.func(in_)
        except Exception as e:
            print(e)
            return None
