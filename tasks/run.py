import asyncio

from golem_core import GolemNode

from tasks.db import DB

from tasks.create_activities import create_activities
from tasks.process_tasks import process_tasks
from tasks.save_new_objects import save_new_objects


async def main(*, payload, get_tasks, results_cnt, dsn):
    db = DB(dsn)

    golem = GolemNode()

    async with golem:
        await db.aexecute("INSERT INTO run (id) VALUES (%s)", (golem.app_session_id,))

        process_tasks_task = asyncio.create_task(process_tasks(golem, db, get_tasks))
        create_activities_task = asyncio.create_task(create_activities(golem, db, payload, 2))
        save_new_objects_task = asyncio.create_task(save_new_objects(golem, db))

        try:
            await process_tasks_task
        finally:
            process_tasks_task.cancel()
            create_activities_task.cancel()
            save_new_objects_task.cancel()
            await asyncio.gather(process_tasks_task, save_new_objects_task, create_activities_task)
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
