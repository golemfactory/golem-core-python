import asyncio
from datetime import datetime, timezone, timedelta

from golem_core.commands import Deploy, Start
from golem_core.mid import (
    SimpleScorer,
    default_negotiate, default_create_agreement, default_create_activity,
)
from golem_core.events import NewResource
from golem_core.low import Allocation


async def score_proposal(proposal):
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


class ActivityManager:
    def __init__(self, golem, db, *, payload, max_activities, max_concurrent=None):
        self.golem = golem
        self.db = db
        self.payload = payload
        self.max_activities = max_activities
        self.max_concurrent = max_concurrent if max_concurrent is not None else max_activities

        self._current_allocation = None
        self._demand_expiration = None
        self._demand = None
        self._initial_proposals = None
        self._create_demand_lock = asyncio.Lock()
        self._initial_proposals_lock = asyncio.Lock()
        self._tasks = []

    ###################
    #   run
    async def run(self):
        async def save_current_allocation(event):
            self._current_allocation = event.resource

        self.golem.event_bus.resource_listen(
            save_current_allocation, event_classes=[NewResource], resource_classes=[Allocation]
        )

        await self.recover()

        try:
            await self._run()
        except asyncio.CancelledError:
            [task.cancel() for task in self._tasks]
            await asyncio.gather(*self._tasks, return_exceptions=True)
            raise

    async def _run(self):
        semaphore = asyncio.BoundedSemaphore(self.max_concurrent)

        while True:
            await semaphore.acquire()

            running_activity_cnt = await self._get_running_activity_cnt()
            running_task_cnt = len([task for task in self._tasks if not task.done()])

            if running_activity_cnt + running_task_cnt < self.max_activities:
                self._tasks.append(asyncio.create_task(self._get_new_activity(semaphore)))
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
            FROM    activities(%(run_id)s) run_act
            JOIN    activity               all_act
                ON  run_act.activity_id = all_act.id
            WHERE   all_act.status = 'READY'
        """)
        return data[0][0]

    ###################################
    #   get_new_activity, demand etc
    async def _get_new_activity(self, semaphore):
        try:
            async def get_proposal():
                return await asyncio.wait_for(self._get_new_proposal(), timeout=30)

            async def negotiate(proposal):
                return await asyncio.wait_for(default_negotiate(proposal), timeout=30)

            async def create_agreement(proposal):
                return await asyncio.wait_for(default_create_agreement(proposal), timeout=30)

            async def create_activity(agreement):
                return await asyncio.wait_for(default_create_activity(agreement), timeout=30)

            async def prepare_activity(activity):
                return await asyncio.wait_for(self._prepare_activity(activity), timeout=300)

            #   Q: Why don't we use golem_core.mid.Chain?
            #   A: This is easier to debug, and there used to be a lot of debugging around here.
            chain_parts = (negotiate, create_agreement, create_activity, prepare_activity)

            awaitable = get_proposal()
            for chain_part in chain_parts:
                awaited = await awaitable
                awaitable = chain_part(awaited)

            awaited = await awaitable
            return awaited
        finally:
            semaphore.release()

    async def _get_new_proposal(self):
        async with self._create_demand_lock:
            if self._demand is None or self._demand_expires_soon():
                old_demand = self._demand
                await self._create_demand()
                if old_demand is not None:
                    asyncio.create_task(old_demand.unsubscribe())

        async with self._initial_proposals_lock:
            return await self._initial_proposals.__anext__()

    def _demand_expires_soon(self):
        assert self._demand_expiration is not None
        #   Q: Why 400 seconds before expiration?
        #   A: No particular reason. Could be 600 could be 300 (but not less than 300,
        #      as we'd got proposals that can't be negotiated then)
        return (self._demand_expiration - datetime.now(timezone.utc)) < timedelta(seconds=400)

    async def _create_demand(self):
        allocation = await self._get_allocation()
        self._demand_expiration = datetime.now(timezone.utc) + timedelta(seconds=1800)
        self._demand = await self.golem.create_demand(
            self.payload, allocations=[allocation], expiration=self._demand_expiration
        )
        scorer = SimpleScorer(score_proposal, min_proposals=10, max_wait=timedelta(seconds=3))
        self._initial_proposals = scorer(self._demand.initial_proposals())

    async def _prepare_activity(self, activity):
        try:
            batch = await activity.execute_commands(Deploy(), Start())
            await batch.wait(timeout=300)
            assert batch.success, batch.events[-1].message
            await self.db.aexecute(
                "UPDATE activity SET status = 'READY' WHERE id = %(activity_id)s",
                {"activity_id": activity.id})
            return activity
        except Exception:
            await self.db.close_activity(activity, 'deploy/start failed')
            raise

    async def _get_allocation(self):
        #   Startup - wait until PaymentManager created an allocation
        while True:
            if self._current_allocation is None:
                await asyncio.sleep(0.1)
            else:
                return self._current_allocation

    ###########################
    #   recovery
    async def recover(self):
        #   This method is called once, when we start.
        #   When it finishes:
        #   *   we don't have any NEW or READY activities
        #   *   we have as single task for each activity that was NEW or READY

        data = await self.db.select("""
            UPDATE  tasks.activity               all_act
            SET     status = 'RECOVERING'
            FROM    tasks.activities(%(run_id)s) our_act
            --  The only pupose of this join is to return the old status
            JOIN    tasks.activity               old_act
                ON  old_act.id = our_act.activity_id
            WHERE   all_act.id = our_act.activity_id
                AND all_act.status IN ('READY', 'NEW')
            RETURNING all_act.id, all_act.agreement_id, old_act.status
        """)

        for activity_id, agreement_id, status in data:
            activity = self.golem.activity(activity_id)
            agreement = self.golem.agreement(agreement_id)
            agreement.add_child(activity)
            if status == "NEW":
                task = asyncio.create_task(self._recreate_activity(activity))
            else:
                task = asyncio.create_task(self._recover_or_recreate_activity(activity))
            self._tasks.append(task)

    async def _recreate_activity(self, activity):
        await self.db.aexecute(
            "UPDATE  tasks.activity SET (status, stop_reason) = ('STOPPING', 'recreating') WHERE id = %(activity_id)s",
            {"activity_id": activity.id},
        )
        await activity.destroy()
        new_activity = await activity.parent.create_activity()
        await asyncio.wait_for(self._prepare_activity(new_activity), timeout=300)

    async def _recover_or_recreate_activity(self, activity):
        data = await self.db.select(
            "SELECT id FROM tasks.batch WHERE activity_id = %(activity_id)s ORDER BY created_ts DESC LIMIT 1",
            {"activity_id": activity.id},
        )
        last_batch = self.golem.batch(data[0][0], activity.id)

        #   TODO: fix this once https://github.com/golemfactory/golem-core-python/issues/49 is done
        last_batch.start_collecting_events()
        await asyncio.sleep(1)

        if last_batch.done:
            await self.db.aexecute(
                "UPDATE activity SET status = 'READY' WHERE id = %(activity_id)s",
                {"activity_id": activity.id})
        else:
            await self._recreate_activity(activity)
