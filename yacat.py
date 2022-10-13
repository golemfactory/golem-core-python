import asyncio

from golem_api import GolemNode
from golem_api.default_logger import DefaultLogger
from golem_api.high.execute_tasks import default_prepare_activity
from golem_api.mid import (
    Buffer, Chain, Map, Zip,
    ActivityPool,
    default_negotiate, default_create_agreement, default_create_activity,
)

from yacat_no_business_logic import PAYLOAD, MAX_WORKERS, main_task_source, tasks_queue


async def async_task_stream():
    while True:
        yield await tasks_queue.get()


async def filter_proposals(proposal_stream):
    async for proposal in proposal_stream:
        print(proposal)
        yield proposal


async def close_agreement_repeat_task(func, args, e):
    activity, task = args
    tasks_queue.put_nowait(task)
    await activity.destroy()
    await activity.parent.terminate()


async def main() -> None:
    asyncio.create_task(main_task_source())

    golem = GolemNode()
    golem.event_bus.listen(DefaultLogger().on_event)

    async with golem:
        allocation = await golem.create_allocation(amount=1)
        demand = await golem.create_demand(PAYLOAD, allocations=[allocation])

        async for result in Chain(
            demand.initial_proposals(),
            filter_proposals,
            Map(default_negotiate),
            Map(default_create_agreement),
            Map(default_create_activity),
            Map(default_prepare_activity),
            ActivityPool(max_size=MAX_WORKERS),
            Zip(async_task_stream()),
            Map(
                lambda activity, task: task.execute(activity),
                on_exception=close_agreement_repeat_task,
            ),
            Buffer(size=MAX_WORKERS + 1),
        ):
            pass

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    task = loop.create_task(main())
    try:
        loop.run_until_complete(task)
    except KeyboardInterrupt:
        task.cancel()
        try:
            loop.run_until_complete(task)
        except asyncio.CancelledError:
            pass
