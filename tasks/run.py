import asyncio

from golem_core import GolemNode

from tasks.db import DB

from tasks.task_executor import TaskExecutor
from tasks.activity_manager import ActivityManager
from tasks.payment_manager import PaymentManager
from tasks.event_writer import EventWriter
from tasks.cost_manager import CostManager
from tasks.event_bus import ParallelEventBus

class Runner:
    def __init__(self, *, payload, get_tasks, results_cnt, dsn, run_id, workers, result_max_price, budget_str):
        self.payload = payload
        self.get_tasks = get_tasks
        self.results_cnt = results_cnt
        self.dsn = dsn
        self.workers = workers
        self.result_max_price = result_max_price
        self.budget_str = budget_str

        self.db = DB(self.dsn, run_id)
        self.golem = GolemNode(app_session_id=self.db.app_session_id)

        #   TODO: this might be moved to `golem_core`, or at least event-bus-setting API will be added.
        #         https://github.com/golemfactory/golem-core-python/issues/3
        self.golem._event_bus = ParallelEventBus()

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

        if self.result_max_price is not None:
            cost_manager = CostManager(golem, db, result_max_price=self.result_max_price)
            cost_manager.start()

        #   Never-ending tasks
        payment_manager = PaymentManager(golem, db, self.budget_str)
        task_executor = TaskExecutor(golem, db, get_tasks=self.get_tasks, max_concurrent=self.workers)
        activity_manager = ActivityManager(golem, db, payload=self.payload, max_activities=self.workers)

        all_tasks = (
            asyncio.create_task(task_executor.run()),
            asyncio.create_task(activity_manager.run()),
            asyncio.create_task(payment_manager.run()),
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
        await asyncio.sleep(1)
        cnt = await results_cnt(db.run_id)
        prev_cnt_data = await db.select("SELECT cnt FROM results WHERE run_id = %(run_id)s ORDER BY id DESC LIMIT 1")
        if prev_cnt_data:
            prev_cnt = prev_cnt_data[0][0]
            if prev_cnt > cnt:
                raise RuntimeError(f"Recent result_cnt {cnt} is lower than previous one {prev_cnt}")
            elif prev_cnt == cnt:
                continue

        #   Q: Why do we INSERT instead of UPDATE? Do we need that many rows here?
        #   A: This allows tracking the app-efficiency-in-time and might be useful for debugging/testing.
        #      E.g. "We're not geting results now, when did we get the last one?".
        await db.aexecute("INSERT INTO results (run_id, cnt) VALUES (%(run_id)s, %(cnt)s)", {"cnt": cnt})


def run(*, payload, get_tasks, results_cnt, dsn, run_id, workers, result_max_price, budget_str):
    runner = Runner(
        payload=payload,
        get_tasks=get_tasks,
        results_cnt=results_cnt,
        dsn=dsn,
        run_id=run_id,
        workers=workers,
        result_max_price=result_max_price,
        budget_str=budget_str,
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
