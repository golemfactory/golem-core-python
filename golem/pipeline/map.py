import asyncio
import inspect
from typing import AsyncIterator, Awaitable, Callable, Generic, Tuple, TypeVar, Union

from golem.pipeline.exceptions import InputStreamExhausted

InType = TypeVar("InType")
OutType = TypeVar("OutType")


async def default_on_exception(func: Callable, args: Tuple, orig_exc: Exception) -> None:
    args_str = ", ".join([str(arg) for arg in args])
    print(f"Exception in {func.__name__}({args_str}): {orig_exc}")


class Map(Generic[InType, OutType]):
    """Turns one async iterator into another async iterator using a provided mapping function.

    Sample usage::

        async def src_func():
            yield 1
            yield 2

        async def map_func(x):
            return x * 2

        async for awaitable_val in Map(map_func)(src_func()):
            print(await awaitable_val)
            #   2
            #   4

    Caveats:
    * Always yields awaitables
    * It doesn't matter if source iterator yields `X` or `Awaitable[X]`, which has two consequences:

       * (good) Maps can be stacked one after another in a :any:`Chain`
       * (bad) Mapping functions that accept an awaitable as an argument should be avoided.

    * If input stream yields tuples, they will be passed to mapping function unpacked

    """

    def __init__(
        self,
        func: Callable[[InType], Awaitable[OutType]],
        *,
        on_exception: Callable[
            [Callable, Tuple, Exception], Awaitable[None]
        ] = default_on_exception,
    ):
        """Init Map.

        :param func: An async function that will be executed on every element of the stream passed
            to :any:`__call__`.
        :param on_exception: An async function that will be executed whenever main function raises
            an exception.
            Defaults to a function that prints the exception.
        """
        self.func = func
        self.on_exception = on_exception

    async def __call__(
        self,
        in_stream: Union[AsyncIterator[InType], AsyncIterator[Awaitable[InType]]],
    ) -> AsyncIterator[Awaitable[OutType]]:
        """Call Map.

        :param in_stream: An async stream of either func args or args-returning awaitables.
        """
        self._in_stream_lock = asyncio.Lock()
        while True:
            yield asyncio.create_task(self._next_value(in_stream))

    async def _next_value(
        self, in_stream: Union[AsyncIterator[InType], AsyncIterator[Awaitable[InType]]]
    ) -> OutType:
        while True:
            async with self._in_stream_lock:
                try:
                    in_val = await in_stream.__anext__()
                except StopAsyncIteration:
                    raise InputStreamExhausted()

            args = await self._as_awaited_tuple(in_val)

            try:
                return await self.func(*args)
            except Exception as e:
                await self.on_exception(self.func, args, e)

    async def _as_awaited_tuple(self, in_val: Union[InType, Awaitable[InType], Tuple]) -> Tuple:
        #   Q: Why this?
        #   A: Because this way it's possible to wait chains of awaitables without
        #      dealing with awaitables at all. E.g. We have Map(X -> Y) followed by Map(Y -> Z)
        #      and first map returns Awaitable[Y], and second map unpacks this Awaitable here.
        #   (This probably has some downsides, but should be worth it)
        if not isinstance(in_val, tuple):
            if inspect.isawaitable(in_val):
                awaited_val = await in_val
                if isinstance(awaited_val, tuple):
                    return awaited_val
                else:
                    return (awaited_val,)
            else:
                return (in_val,)
        else:
            new_vals = []
            for single_val in in_val:
                if inspect.isawaitable(single_val):
                    single_val = await single_val
                new_vals.append(single_val)
            return tuple(new_vals)
