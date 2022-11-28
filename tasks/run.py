import asyncio

from golem_api import GolemNode

from tasks.db import DB

from tasks.process_tasks import process_tasks
from tasks.save_new_objects import save_new_objects


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
