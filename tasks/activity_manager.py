import asyncio

from golem_core.mid import (
    Chain, Map,
    default_negotiate, default_create_agreement, default_create_activity, default_prepare_activity,
)

class ActivityManager:
    def __init__(self, golem, db, *, payload, max_activities, max_concurrent=2):
        self.golem = golem
        self.db = db
        self.payload = payload
        self.max_activities = max_activities
        self.max_concurrent = max_concurrent

    async def run(self):
        chain = await self._get_chain()
        tasks = []

        semaphore = asyncio.BoundedSemaphore(self.max_concurrent)
        chain_lock = asyncio.Lock()
        while True:
            await semaphore.acquire()

            running_activity_cnt = await self._get_running_activity_cnt()
            running_task_cnt = len([task for task in tasks if not task.done()])

            if running_activity_cnt + running_task_cnt < self.max_activities:
                tasks.append(asyncio.create_task(self._get_new_activity(chain_lock, chain, semaphore)))
            else:
                semaphore.release()
                await asyncio.sleep(1)

    async def _get_running_activity_cnt(self):
        #   Q: why don't we use golem.all_resources(Activity) here?
        #   A: because:
        #   *   this works without changes after a restart
        #   *   database contents are higher quality than temporary object states
        #       (e.g. we might have some other entity that changes the database only)
        data = await self.db.select("""
            SELECT  count(*)
            FROM    activities(%s) run_act
            JOIN    activity       all_act
                ON  run_act.activity_id = all_act.id
            WHERE   all_act.status != 'CLOSED'
        """, (self.golem.app_session_id,))
        return data[0][0]

    async def _prepare_activity(self, activity):
        await default_prepare_activity(activity)
        await self.db.aexecute("""
            UPDATE  activity
            SET     status = 'READY'
            WHERE   id = %s
        """, (activity.id,))
        return activity

    async def _get_chain(self):
        allocation = await self.golem.create_allocation(amount=1)
        demand = await self.golem.create_demand(self.payload, allocations=[allocation])

        chain = Chain(
            demand.initial_proposals(),
            Map(default_negotiate),
            Map(default_create_agreement),
            Map(default_create_activity),
            Map(self._prepare_activity),
        )
        return chain

    async def _get_new_activity(self, chain_lock, chain, semaphore):
        try:
            async with chain_lock:
                activity_awaitable = await chain.__anext__()
            await activity_awaitable
        finally:
            semaphore.release()
