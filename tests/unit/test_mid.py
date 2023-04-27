from typing import Any, AsyncIterator, Callable, Tuple

import pytest

from golem_core.pipeline import Buffer, Chain, Limit, Map, Zip


async def src() -> AsyncIterator[int]:
    for x in range(10):
        yield x


async def src_2() -> AsyncIterator[str]:
    for x in "abcde":
        yield x


async def identity(x: Any) -> Any:
    return x


async def max_3(val: int) -> int:
    if val > 3:
        raise ValueError
    return val


@pytest.mark.parametrize(
    "expected_cnt, chain_middle_parts",
    (
        (10, ()),
        (3, (Limit(3),)),
        (4, (Limit(4), Map(identity))),
        (3, (Map(identity), Limit(3))),
        (10, (Buffer(2), Map(identity))),
        (7, (Limit(7), Buffer(2), Map(identity))),
        (4, (Map(max_3), Limit(7))),
        (10, (Zip(src()),)),
        (5, (Zip(src_2()),)),
        (3, (Limit(3), Zip(src_2()))),
        (3, (Limit(3), Map(identity), Zip(src_2()))),
        (3, (Zip(src_2()), Limit(3))),
        (4, (Map(max_3), Zip(src_2()))),
        (2, (Limit(7), Map(max_3), Limit(2), Zip(src_2()))),
        (4, (Map(max_3), Map(identity))),
    ),
)
@pytest.mark.asyncio
async def test_finite_chain(expected_cnt: int, chain_middle_parts: Tuple[Callable]) -> None:
    """Create some finite chains.

    Ensure there are no errors & correct amounts of items are returned.
    """

    chain = Chain(src(), *chain_middle_parts, Buffer(2))

    cnt = 0
    async for _ in chain:
        cnt += 1

    assert cnt == expected_cnt
