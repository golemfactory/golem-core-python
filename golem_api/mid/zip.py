from typing import AsyncIterator, Tuple, TypeVar

X = TypeVar("X")
Y = TypeVar("Y")


class Zip:
    """Merges two async iterators into a single async iterator.

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

    It is currently assumed stream passed to `__call__` yields at least as many values
    as the stream passed to `__init__` - this is a TODO.
    """

    def __init__(self, main_stream: AsyncIterator[X]):
        self._main_stream = main_stream

    async def __call__(self, other_stream: AsyncIterator[Y]) -> AsyncIterator[Tuple[Y, X]]:
        async for main_value in self._main_stream:
            other_value = await other_stream.__anext__()
            yield other_value, main_value  # type: ignore  # mypy, why?
