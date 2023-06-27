from typing import Any, AsyncIterator, Callable


class Chain:
    """Wrapper class for mid-level components that utilize the pipes and filters pattern.

    Sample usage::

        async def source() -> AsyncIterator[int]:
            yield 1
            yield 2

        async def int_2_str(numbers: AsyncIterator[int]) -> AsyncIterator[str]:
            async for number in numbers:
                yield str(number)

        async for x in Chain(source, int_2_str):
            # x == "1"
            # x == "2"

    A more Golem-specific usage::

        from golem import GolemNode, RepositoryVmPayload
        from golem.mid import (
            Buffer, Chain, Map,
            default_negotiate, default_create_agreement, default_create_activity
        )

        BUDGET = 1
        PAYLOAD = RepositoryVmPayload("9a3b5d67b0b27746283cb5f287c13eab1beaa12d92a9f536b747c7ae")

        async def main():
            async with GolemNode() as golem:
                allocation = await golem.create_allocation(BUDGET)
                demand = await golem.create_demand(PAYLOAD, allocations=[allocation])

                async for activity in Chain(
                    demand.initial_proposals(),
                    Map(default_negotiate),
                    Map(default_create_agreement),
                    Map(default_create_activity),
                    Buffer(),
                ):
                    print(activity)

    """

    def __init__(
        self,
        chain_start: AsyncIterator[Any],
        *pipes: Callable[[AsyncIterator[Any]], AsyncIterator[Any]],
    ):
        aiter = chain_start

        for pipe in pipes:
            aiter = pipe(aiter)

        self._aiter = aiter

    def __aiter__(self) -> "Chain":
        return self

    async def __anext__(self) -> Any:
        return await self._aiter.__anext__()
