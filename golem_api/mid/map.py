from typing import AsyncIterator, Awaitable, Callable, TypeVar


InType = TypeVar("InType")
OutType = TypeVar("OutType")


class Map:
    def __init__(self, func: Callable[[InType], Awaitable[OutType]]):
        self.func = func

    async def __call__(self, in_stream: AsyncIterator[InType]) -> AsyncIterator[OutType]:
        async for in_ in in_stream:
            yield await self.func(in_)
