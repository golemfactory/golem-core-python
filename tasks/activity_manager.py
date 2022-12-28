import asyncio
from datetime import datetime, timezone, timedelta

from golem_core.commands import Deploy, Start
from golem_core.mid import (
    Chain, Map, SimpleScorer,
    default_negotiate, default_create_agreement, default_create_activity,
)
from golem_core.low.exceptions import BatchError, BatchTimeoutError

class ActivityManager:
    def __init__(self, golem, db, *, payload, max_activities, max_concurrent=None):
        self.golem = golem
        self.db = db
        self.payload = payload
        self.max_activities = max_activities
        self.max_concurrent = max_concurrent if max_concurrent is not None else max_activities

        self._demand_expiration = None
        self._chain = None
        self._get_chain_lock = asyncio.Lock()
        self._tasks = []

    async def run(self):
        try:
            await self._run()
        except asyncio.CancelledError:
            [task.cancel() for task in self._tasks]
            await asyncio.gather(*self._tasks, return_exceptions=True)
            raise

    async def _run(self):
        semaphore = asyncio.BoundedSemaphore(self.max_concurrent)
        chain_lock = asyncio.Lock()

        async def x():
            while True:
                await asyncio.sleep(1)
                print("CNT", len([t for t in self._tasks if not t.done()]))
                print(sorted(t.get_name() for t in self._tasks if not t.done()))

        asyncio.create_task(x())

        while True:
            await semaphore.acquire()

            running_activity_cnt = await self._get_running_activity_cnt()
            running_task_cnt = len([task for task in self._tasks if not task.done()])

            if running_activity_cnt + running_task_cnt < self.max_activities:
                chain = await self._get_chain()
                self._tasks.append(asyncio.create_task(self._get_new_activity(chain, chain_lock, semaphore)))
            else:
                semaphore.release()
                await asyncio.sleep(1)

    async def recover(self):
        #   Recoverable
        our_ready_activities = await self.db.select("""
            UPDATE  tasks.activity all_act
            SET     status = 'RECOVERING'
            FROM    tasks.activities(%(run_id)s) our_act
            WHERE   all_act.id     = our_act.activity_id
                AND all_act.status = 'READY'
            RETURNING all_act.id
        """)

        #   Unrecoverable
        await self.db.aexecute("""
            UPDATE  tasks.activity all_act
            SET     (status, stop_reason) = ('STOPPED', 'could not recover from status ' || status)
            FROM    tasks.activities(%(run_id)s) our_act
            WHERE   all_act.id     = our_act.activity_id
                AND all_act.status NOT IN ('STOPPED', 'RECOVERING')
        """)

        for activity_id in [row[0] for row in our_ready_activities]:
            asyncio.create_task(self._recover_activity(activity_id))

    async def _recover_activity(self, activity_id):
        #   Activity has now state "RECOVERING".
        #   We're waiting for the last batch to finish at most 30s, if it finishes
        #   (or is already finished) we set it to "READY", if not - we try to close the
        #   activity.
        agreement_id = (await self.db.select("""
            SELECT  agreement_id
            FROM    tasks.activity
            WHERE   id = %(activity_id)s
        """, {"activity_id": activity_id}))[0][0]

        batch_id = (await self.db.select("""
            SELECT  id
            FROM    tasks.batch
            WHERE   activity_id = %(activity_id)s
            ORDER BY created_ts DESC
            LIMIT 1
        """, {"activity_id": activity_id}))[0][0]

        agreement = self.golem.agreement(agreement_id)
        batch = self.golem.batch(batch_id, activity_id)

        try:
            #   FIXME: This never succeeds. Why?
            #          (Also: maybe we'd rather destroy & recreate activity?)
            batch.start_collecting_events()
            await batch.wait(30)
            await self.db.aexecute("""
                UPDATE  tasks.activity
                SET     status = 'READY'
                WHERE   id = %(activity_id)s
            """, {"activity_id": activity_id})
        except (BatchError, BatchTimeoutError):
            await agreement.close_all()
            await self.db.aexecute("""
                UPDATE  tasks.activity
                SET     (status, stop_reason) = ('STOPPED', 'recovery failed')
                WHERE   id = %(activity_id)s
            """, {"activity_id": activity_id})

    async def _get_running_activity_cnt(self):
        #   Q: why don't we use golem.all_resources(Activity) here?
        #   A: because:
        #   *   this works without changes after a restart
        #   *   database contents are higher quality than temporary object states
        #       (e.g. we might have some other entity that changes the database only)
        data = await self.db.select("""
            SELECT  count(*)
            FROM    activities(%(run_id)s) run_act
            JOIN    activity       all_act
                ON  run_act.activity_id = all_act.id
            WHERE   all_act.status IN ('NEW', 'READY')
        """)
        return data[0][0]

    async def _prepare_activity(self, activity):
        try:
            batch = await activity.execute_commands(Deploy(), Start())
            await batch.wait(timeout=300)
            assert batch.success, batch.events[-1].message
            await self.db.aexecute(
                "UPDATE activity SET status = 'READY' WHERE id = %(activity_id)s",
                {"activity_id": activity.id})
        except Exception:
            print("DEPLOY/START FAILED")
            await self.db.close_activity(activity, 'deploy/start failed')

    async def _get_chain(self):
        async with self._get_chain_lock:
            if self._chain is None or (await self._demand_expires_soon()):
                self._chain = await self._create_new_chain()
        return self._chain

    async def _demand_expires_soon(self):
        assert self._demand_expiration is not None
        return (self._demand_expiration - datetime.now(timezone.utc)) < timedelta(seconds=300)

    async def _create_new_chain(self):
        #   TODO
        #   1.  We now create a new allocation for each chain
        #   2.  We don't terminate old allocations (only when app exits)
        #   both seems wrong, but we must first decide about whole budgeting thing.
        allocation = await self.golem.create_allocation(amount=1)

        self._demand_expiration = datetime.now(timezone.utc) + timedelta(seconds=1800)
        demand = await self.golem.create_demand(
            self.payload, allocations=[allocation], expiration=self._demand_expiration
        )

        async def negotiate(proposal):
            return await asyncio.wait_for(default_negotiate(proposal), timeout=10)

        async def create_agreement(proposal):
            return await asyncio.wait_for(default_create_agreement(proposal), timeout=10)

        async def create_activity(agreement):
            return await asyncio.wait_for(default_create_activity(agreement), timeout=10)

        chain = Chain(
            demand.initial_proposals(),
            SimpleScorer(self._score_proposal, min_proposals=10),
            Map(negotiate),
            Map(create_agreement),
            Map(create_activity),
            Map(self._prepare_activity),
        )
        return chain

    async def _get_new_activity(self, chain, chain_lock, semaphore):
        try:
            async with chain_lock:
                activity_awaitable = await chain.__anext__()
            await activity_awaitable
        finally:
            semaphore.release()

    @staticmethod
    async def _score_proposal(proposal):
        MAX_LINEAR_COEFFS = [0.001, 0.001, 0]

        properties = proposal.data.properties
        if properties['golem.com.pricing.model'] != 'linear':
            return None

        coeffs = properties['golem.com.pricing.model.linear.coeffs']
        for val, max_val in zip(coeffs, MAX_LINEAR_COEFFS):
            if val > max_val:
                return None
        else:
            return 1 - (coeffs[0] + coeffs[1])
