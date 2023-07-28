from typing import AsyncIterator, TypeVar

X = TypeVar("X")


class Limit:
    """Limits the number of elements returned by an async generator.

    Sample usage::

        async def yield_thrice():
            yield "foo"
            yield "bar"
            yield "baz"

        # only "foo" and "bar" will be printed
        async for x in Chain(
            yield_thrice(),
            Limit(2),
        ):
            print(x)
    """

    def __init__(self, max_items: int = 1):
        """Init Limit.

        :param max_items: Maximum number of items yielded
        """
        self.max_items = max_items

    async def __call__(self, stream: AsyncIterator[X]) -> AsyncIterator[X]:
        cnt = 0
        async for val in stream:
            yield val
            cnt += 1
            if cnt == self.max_items:
                break
