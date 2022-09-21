from typing import AsyncIterator, Tuple, TypeVar

X = TypeVar("X")
Y = TypeVar("Y")


class Zip:
    def __init__(self, main_stream: AsyncIterator[X]):
        self._main_stream = main_stream

    async def __call__(self, other_stream: AsyncIterator[Y]) -> AsyncIterator[Tuple[Y, X]]:
        async for main_value in self._main_stream:
            other_value = await other_stream.__anext__()
            yield other_value, main_value  # type: ignore  # mypy, why?
