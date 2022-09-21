import asyncio
import inspect
from typing import AsyncIterator, Awaitable, Generic, TypeVar, Callable, Union

InType = TypeVar("InType")
OutType = TypeVar("OutType")


class Map(Generic[InType, OutType]):
    def __init__(self, func: Callable[[InType], Awaitable[OutType]], return_awaitable: bool = True):
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
        #   1.  Get a value from in_stream
        #   2.  If it is awaitable, await it
        #   3.  Execute self.func on it
        #   4.  Return first result that is not None
        while True:
            in_val = await self._next_from_stream(in_stream)
            if inspect.isawaitable(in_val):
                in_val = await in_val

            try:
                return await self.func(in_val)  # type: ignore
            except Exception as e:
                #   TODO: emit MapFailed event (? - where is the event emitter?)
                print("Map exception", type(e).__name__, str(e))

    async def _next_from_stream(
        self, in_stream: Union[AsyncIterator[InType], AsyncIterator[Awaitable[InType]]],
    ) -> Union[InType, Awaitable[InType]]:
        async with self._in_stream_lock:
            return await in_stream.__anext__()  # type: ignore  # mypy, why?
