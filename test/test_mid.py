import pytest

from golem_api.mid import Buffer, Chain, Limit, Map, Zip

async def src():
    for x in range(10):
        yield x

async def identity(x):
    return x


@pytest.mark.parametrize("expected_cnt, chain_middle_parts", (
    (10, ()),
    (3, (Limit(3),)),
    (4, (Limit(4), Map(identity))),
    (3, (Map(identity), Limit(3))),
    (10, (Buffer(2), Map(identity))),
    (7, (Limit(7), Buffer(2), Map(identity))),
))
@pytest.mark.parametrize("buffer_size", (1, 2, 4, 20))
@pytest.mark.asyncio
async def test_limit(expected_cnt, chain_middle_parts, buffer_size):
    chain = Chain(src(), *chain_middle_parts, Buffer(buffer_size))

    cnt = 0
    async for _ in chain:
        cnt += 1

    assert cnt == expected_cnt
