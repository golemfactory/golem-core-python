from golem_api.mid import (
    Chain, Map, ActivityPool, Zip, Buffer,
    default_negotiate, default_create_agreement, default_create_activity, default_prepare_activity,
)

async def process_task(activity, task):
    return await task(activity)

async def process_tasks(golem, payload, get_tasks) -> None:
    async def aget_tasks():
        for task in get_tasks():
            yield task

    allocation = await golem.create_allocation(amount=1)
    demand = await golem.create_demand(payload, allocations=[allocation])

    async for _ in Chain(
        demand.initial_proposals(),
        Map(default_negotiate),
        Map(default_create_agreement),
        Map(default_create_activity),
        Map(default_prepare_activity),
        ActivityPool(2),
        Zip(aget_tasks()),
        Map(process_task),
        Buffer(size=2),
    ):
        pass
