import asyncio
import inspect
from typing import AsyncIterator, Awaitable, Tuple, TypeVar, Union

X = TypeVar("X")
Y = TypeVar("Y")


class Zip:
    """Merges two async iterators into a single async iterator.

    If value from any of the iterators is an awaitable, yielded value is a
    tuple-returning awaitable. If all values are non-awaitables, yielded value is a tuple.

    If streams have different lengths, there will be as many pairs as there are items in the shorter
    one.

    Sample usage::

        async def str_stream():
            yield "foo"
            yield "bar"

        async def int_stream():
            yield 1
            yield 2

        async for pair in Zip(int_stream())(str_stream()):
            print(pair)
            #   ("foo", 1)
            #   ("bar", 2)

    Or with an awaitable::

        async def get_x():
            return "baz"

        async def str_stream():
            yield get_x()
            yield get_x()

        async def int_stream():
            yield 1
            yield 2

        async for awaitable_pair in Zip(int_stream())(str_stream()):
            print(await awaitable_pair)
            #   ("baz", 1)
            #   ("baz", 2)
    """

    def __init__(self, main_stream: AsyncIterator[Union[X, Awaitable[X]]]):
        self._main_stream = main_stream

    async def __call__(
        self, other_stream: AsyncIterator[Union[Y, Awaitable[Y]]]
    ) -> AsyncIterator[Union[Tuple[Y, X], Awaitable[Tuple[Y, X]]]]:
        async for main_value in self._main_stream:
            try:
                other_value = await other_stream.__anext__()
            except StopAsyncIteration:
                break

            if any(inspect.isawaitable(val) for val in (main_value, other_value)):
                yield self._merge_awaitables(other_value, main_value)  # type: ignore
            else:
                yield other_value, main_value  # type: ignore

    async def _merge_awaitables(
        self, val_1: Union[Y, Awaitable[Y]], val_2: Union[X, Awaitable[X]]
    ) -> Awaitable[Tuple[Y, X]]:
        if inspect.isawaitable(val_1):
            if inspect.isawaitable(val_2):
                values = await asyncio.gather(val_1, val_2)
            else:
                values = (await val_1, val_2)
        elif inspect.isawaitable(val_2):
            values = (val_1, await val_2)
        else:
            values = (val_1, val_2)

        return tuple(values)  # type: ignore
