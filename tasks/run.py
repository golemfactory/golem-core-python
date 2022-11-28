import asyncio

from golem_api import GolemNode
from golem_api.mid import (
    Chain, Map, ActivityPool, Zip, Buffer,
    default_negotiate, default_create_agreement, default_create_activity, default_prepare_activity,
)

from tasks.db import DB


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

async def save_new_objects(golem, db):
    from golem_api.low import Demand
    from golem_api.events import NewResource

    async def save_resource(event):
        db.execute("INSERT INTO demand (id, run_id) VALUES (%s, %s)", (event.resource.id, golem.app_session_id))

    golem.event_bus.resource_listen(save_resource, event_classes=[NewResource], resource_classes=[Demand])

    await asyncio.Future()

async def main(*, payload, get_tasks, results_cnt, dsn):
    db = DB(dsn)

    golem = GolemNode()

    async with golem:
        await db.aexecute("INSERT INTO run (id) VALUES (%s)", (golem.app_session_id,))
        main_task = asyncio.create_task(process_tasks(golem, payload, get_tasks))
        save_new_objects_task = asyncio.create_task(save_new_objects(golem, db))

        try:
            await main_task
        finally:
            main_task.cancel()
            save_new_objects_task.cancel()
            await asyncio.gather(main_task, save_new_objects_task)
            await db.aclose()


def run(*, payload, get_tasks, results_cnt, dsn):
    loop = asyncio.get_event_loop()
    task = loop.create_task(main(
        payload=payload,
        get_tasks=get_tasks,
        results_cnt=results_cnt,
        dsn=dsn,
    ))
    try:
        loop.run_until_complete(task)
    except KeyboardInterrupt:
        task.cancel()
        try:
            loop.run_until_complete(task)
        except asyncio.CancelledError:
            pass
