import asyncio

from golem_core import GolemNode

from tasks.db import DB

from tasks.task_executor import TaskExecutor
from tasks.activity_manager import ActivityManager
from tasks.event_writer import EventWriter

class Runner:
    def __init__(self, *, payload, get_tasks, results_cnt, dsn, run_id):
        self.payload = payload
        self.get_tasks = get_tasks
        self.results_cnt = results_cnt
        self.dsn = dsn

        self.db = DB(self.dsn)
        if run_id is None:
            self.golem = GolemNode()
        else:
            self.golem = GolemNode(app_session_id=run_id)

    async def main(self):
        try:
            await self._main()
        finally:
            await self.db.aclose()

    async def _main(self):
        golem = self.golem
        db = self.db

        await db.aexecute("INSERT INTO run (id) VALUES (%s) ON CONFLICT DO NOTHING", (golem.app_session_id,))

        async with golem:
            task_executor = TaskExecutor(golem, db, get_tasks=self.get_tasks, max_concurrent=2)
            activity_manager = ActivityManager(golem, db, payload=self.payload, max_activities=2)
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


def run(*, payload, get_tasks, results_cnt, dsn, run_id):
    runner = Runner(
        payload=payload,
        get_tasks=get_tasks,
        results_cnt=results_cnt,
        dsn=dsn,
        run_id=run_id,
    )
    loop = asyncio.get_event_loop()
    task = loop.create_task(runner.main())
    try:
        loop.run_until_complete(task)
    except KeyboardInterrupt:
        task.cancel()
        try:
            loop.run_until_complete(task)
        except asyncio.CancelledError:
            pass
