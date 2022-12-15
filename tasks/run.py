import asyncio

from golem_core import GolemNode

from tasks.db import DB

from tasks.task_executor import TaskExecutor
from tasks.activity_manager import ActivityManager
from tasks.payment_manager import PaymentManager
from tasks.event_writer import EventWriter

class Runner:
    def __init__(self, *, payload, get_tasks, results_cnt, dsn, run_id, workers):
        self.payload = payload
        self.get_tasks = get_tasks
        self.results_cnt = results_cnt
        self.dsn = dsn
        self.workers = workers

        self.db = DB(self.dsn, run_id)
        self.golem = GolemNode(app_session_id=self.db.app_session_id)

    async def main(self):
        try:
            await self.db.init_run()
            await self.golem.start()
            await self._main()
        finally:
            await self.golem.aclose()
            await self.db.aclose()

    async def _main(self):
        golem = self.golem
        db = self.db

        #   Logic based on event listeners only
        event_writer = EventWriter(golem, db)
        event_writer.start()

        payment_manager = PaymentManager(golem, db)
        payment_manager.start()

        #   Never-ending tasks
        task_executor = TaskExecutor(golem, db, get_tasks=self.get_tasks, max_concurrent=self.workers)
        activity_manager = ActivityManager(golem, db, payload=self.payload, max_activities=self.workers)

        all_tasks = (
            asyncio.create_task(task_executor.run()),
            asyncio.create_task(activity_manager.run()),
            asyncio.create_task(_save_results_cnt(golem, db, self.results_cnt)),
        )

        try:
            await asyncio.wait(all_tasks, return_when=asyncio.FIRST_COMPLETED)

            for task in all_tasks:
                if task.done() and task.exception():
                    print("Shutting down because of", task.exception())
                    raise task.exception()

            print("All tasks done")
        finally:
            [task.cancel() for task in all_tasks]
            await asyncio.gather(*all_tasks, return_exceptions=True)

            await payment_manager.terminate_agreements()
            await payment_manager.wait_for_invoices()

async def _save_results_cnt(golem, db, results_cnt):
    while True:
        cnt = results_cnt(db.run_id)
        await db.aexecute("INSERT INTO results (run_id, cnt) VALUES (%(run_id)s, %(cnt)s)", {"cnt": cnt})
        await asyncio.sleep(1)


def run(*, payload, get_tasks, results_cnt, dsn, run_id, workers):
    runner = Runner(
        payload=payload,
        get_tasks=get_tasks,
        results_cnt=results_cnt,
        dsn=dsn,
        run_id=run_id,
        workers=workers,
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
