import asyncio
import inspect
from typing import AsyncIterator, Awaitable, Generic, TypeVar, Callable, Tuple, Union

InType = TypeVar("InType")
OutType = TypeVar("OutType")


async def default_on_exception(func: Callable, args: Tuple, orig_exc: Exception):
    args_str = ", ".join([str(arg) for arg in args])
    print(f"Exception in {func.__name__}({args_str}): {orig_exc}")


class Map(Generic[InType, OutType]):
    def __init__(
        self,
        func: Callable[[InType], Awaitable[OutType]],
        *,
        return_awaitable: bool = True,
        on_exception: Callable[[Callable, Tuple, Exception], Awaitable[None]] = default_on_exception,
    ):
        self.func = func
        self.return_awaitable = return_awaitable
        self.on_exception = on_exception

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

            args = await self._as_awaited_tuple(in_val)

            try:
                return await self.func(*args)
            except Exception as e:
                await self.on_exception(self.func, args, e)

    async def _as_awaited_tuple(self, in_val) -> Tuple:
        #   Q: Why this?
        #   A: Because this way it's possible to wait chains of awaitables without
        #      dealing with awaitables at all. E.g. We have Map(X -> Y) followed by Map(Y -> Z)
        #      and first map returns Awaitable[Y] (because of return_awaitable = True),
        #      and second map unpacks this Awaitable here.
        #   (This probably has some downsides, but should be worth it)
        if not isinstance(in_val, tuple):
            in_val = (in_val,)

        new_vals = []
        for single_val in in_val:
            if inspect.isawaitable(single_val):
                single_val = await single_val
            new_vals.append(single_val)
        return tuple(new_vals)
