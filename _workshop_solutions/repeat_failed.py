import asyncio

from golem_api import GolemNode, Payload
from golem_api.mid import (
    Buffer, Chain, Limit, Map,
    default_negotiate, default_create_agreement, default_create_activity, default_prepare_activity
)

from workshop_internals import ActivityPool, execute_task


PAYLOAD = Payload.from_image_hash("9a3b5d67b0b27746283cb5f287c13eab1beaa12d92a9f536b747c7ae")
TASK_DATA = list(range(6))


async def task_stream():
    while True:
        if TASK_DATA:
            yield TASK_DATA.pop()
        else:
            await asyncio.sleep(0.1)

async def repeat_task(func, args, e):
    task = args[0]  # e.task_data would also work
    print(f"Repeating {task} because of {e}")
    TASK_DATA.append(task)

async def main() -> None:
    golem = GolemNode()

    async with golem:
        allocation = await golem.create_allocation(1)
        demand = await golem.create_demand(PAYLOAD, allocations=[allocation])

        new_activity_chain = Chain(
            demand.initial_proposals(),
            Map(default_negotiate),
            Map(default_create_agreement),
            Map(default_create_activity),
            Map(default_prepare_activity),
            Limit(2),
            Buffer(2),
        )

        activity_pool = ActivityPool()
        activity_pool.consume_activities(new_activity_chain)

        task_cnt = len(TASK_DATA)
        result_cnt = 0

        async for task_data, result in Chain(
            task_stream(),
            Map(activity_pool.execute_in_pool(execute_task), on_exception=repeat_task),
            Buffer(10),
        ):
            print(f"{task_data} -> {result}")
            result_cnt += 1
            if result_cnt == task_cnt:
                break

    print("SUCCESS")


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
