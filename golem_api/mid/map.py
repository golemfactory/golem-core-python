import asyncio
import inspect
from typing import Any, AsyncIterator, Awaitable, Generic, TypeVar, Callable, Tuple, Union

InType = TypeVar("InType")
OutType = TypeVar("OutType")


class MapException(Exception):
    def __init__(self, func: Callable, func_args: Tuple[Any], orig_exc: Exception):
        self.func = func
        self.func_args = func_args
        self.orig_exc = orig_exc

        func_args_str = ", ".join([str(arg) for arg in func_args])
        msg = f"{type(self).__name__} in {func.__name__}({func_args_str}): {orig_exc}"
        super().__init__(msg)


class Map(Generic[InType, OutType]):
    def __init__(
        self,
        func: Callable[[InType], Awaitable[OutType]],
        *,
        return_awaitable: bool = True,
        return_exceptions: bool = False,
    ):
        self.func = func
        self.return_awaitable = return_awaitable
        self.return_exceptions = return_exceptions

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
                new_exc = MapException(self.func, args, e)
                if self.return_exceptions:
                    return new_exc
                else:
                    print(new_exc)

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
