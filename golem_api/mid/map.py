import asyncio
import inspect
from typing import AsyncIterator, Awaitable, Generic, TypeVar, Callable, Union

InType = TypeVar("InType")
OutType = TypeVar("OutType")


class Map(Generic[InType, OutType]):
    def __init__(self, func: Callable[[InType], Awaitable[OutType]], *, return_awaitable: bool = True):
        self.func = func
        self.return_awaitable = return_awaitable

        self._in_stream_lock = asyncio.Lock()

    async def __call__(
        self,
        in_stream: Union[AsyncIterator[InType], AsyncIterator[Awaitable[InType]]],
    ) -> Union[AsyncIterator[OutType], AsyncIterator[Awaitable[OutType]]]:
        while True:
            result_coroutine: Awaitable[OutType] = self._next_value(in_stream)
            if self.return_awaitable:
                yield asyncio.create_task(result_coroutine)  # type: ignore  # mypy, why?
            else:
                yield await result_coroutine

    async def _next_value(
        self,
        in_stream: Union[AsyncIterator[InType], AsyncIterator[Awaitable[InType]]],
    ) -> OutType:
        while True:
            async with self._in_stream_lock:
                in_val = await in_stream.__anext__()

            #   Q: Why this?
            #   A: Because this way it's possible to wait chains of awaitables without
            #      dealing with awaitables at all. E.g. We have Map(X -> Y) followed by Map(Y -> Z)
            #      and first map returns Awaitable[Y] (because of return_awaitable = True),
            #      and second map unpacks this Awaitable here.
            #   (This probably has some downsides, but should be worth it)
            if inspect.isawaitable(in_val):
                in_val = await in_val

            try:
                return await self.func(in_val)
            except Exception as e:
                #   TODO: emit MapFailed event (? - where is the event emitter?)
                print("Map exception", type(e).__name__, str(e))
