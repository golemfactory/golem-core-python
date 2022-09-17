import asyncio
import inspect
from typing import AsyncIterator, Awaitable, Generic, Optional, TypeVar, Callable, Union


InType = TypeVar("InType")
OutType = TypeVar("OutType")


class Map(Generic[InType, OutType]):
    def __init__(self, func: Callable[[InType], Awaitable[Optional[OutType]]], async_: bool):
        self.func = func
        self.async_ = async_

    async def __call__(
        self,
        in_stream: Union[AsyncIterator[InType], AsyncIterator[Awaitable[InType]]],
    ) -> Union[AsyncIterator[OutType], AsyncIterator[Awaitable[OutType]]]:
        while True:
            result_coroutine: Awaitable[OutType] = self._next_value(in_stream)
            if self.async_:
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
                result = await self.func(in_val)  # type: ignore
                if result is not None:
                    return result
            except Exception as e:
                print(e)

    @staticmethod
    async def _next_from_stream(
        in_stream: Union[AsyncIterator[InType], AsyncIterator[Awaitable[InType]]],
    ) -> Union[InType, Awaitable[InType]]:
        #   TODO: this is ugly, but fixes the "anext(): asynchronous generator is already running: exception
        #   TODO: overload maybe?
        while True:
            try:
                return await in_stream.__anext__()  # type: ignore  # mypy, why?
            except RuntimeError:
                await asyncio.sleep(0.01)
                continue
