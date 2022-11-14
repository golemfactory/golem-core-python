from typing import AsyncIterator, TypeVar

X = TypeVar("X")


class Limit:
    def __init__(self, max_items: int = 1):
        self.max_items = max_items

    async def __call__(self, stream: AsyncIterator[X]) -> AsyncIterator[X]:
        cnt = 0
        async for val in stream:
            yield val
            cnt += 1
            if cnt == self.max_items:
                break
