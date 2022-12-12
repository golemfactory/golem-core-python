import asyncio

from golem_core import GolemNode

from tasks.db import DB

from tasks.task_executor import TaskExecutor
from tasks.activity_manager import ActivityManager
from tasks.event_writer import EventWriter


async def main(*, payload, get_tasks, results_cnt, dsn):
    db = DB(dsn)

    golem = GolemNode()

    async with golem:
        await db.aexecute("INSERT INTO run (id) VALUES (%s)", (golem.app_session_id,))

        task_executor = TaskExecutor(golem, db, get_tasks=get_tasks, max_concurrent=2)
        activity_manager = ActivityManager(golem, db, payload=payload, max_activities=2)
        event_writer = EventWriter(golem, db)

        execute_tasks_task = asyncio.create_task(task_executor.run())
        manage_activities_task = asyncio.create_task(activity_manager.run())
        event_writer_task = asyncio.create_task(event_writer.run())

        try:
            await execute_tasks_task
        finally:
            execute_tasks_task.cancel()
            manage_activities_task.cancel()
            event_writer_task.cancel()
            await asyncio.gather(execute_tasks_task, manage_activities_task, event_writer_task)
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
