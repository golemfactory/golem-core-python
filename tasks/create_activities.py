import asyncio

from golem_api.mid import (
    Chain, Map,
    default_negotiate, default_create_agreement, default_create_activity, default_prepare_activity,
)

def get_prepare_activity(db):
    async def prepare_activity(activity):
        await default_prepare_activity(activity)
        await db.aexecute("""
            UPDATE  activity
            SET     status = 'READY'
            WHERE   id = %s
        """, (activity.id,))
        return activity
    return prepare_activity

async def get_chain(golem, db, payload):
    allocation = await golem.create_allocation(amount=1)
    demand = await golem.create_demand(payload, allocations=[allocation])

    chain = Chain(
        demand.initial_proposals(),
        Map(default_negotiate),
        Map(default_create_agreement),
        Map(default_create_activity),
        Map(get_prepare_activity(db)),
    )
    return chain

async def get_new_activity(chain_lock, chain, semaphore):
    try:
        async with chain_lock:
            activity_awaitable = await chain.__anext__()
        await activity_awaitable
    finally:
        semaphore.release()

async def get_running_activity_cnt(db, app_session_id):
    #   Q: why don't we use golem.all_resources(Activity) here?
    #   A: because:
    #   *   this works without changes after restart
    #   *   database contents are higher quality than temporary object states
    #       (e.g. we might have some other entity that changes the database only)
    data = await db.select("""
        SELECT  count(*)
        FROM    activities(%s) run_act
        JOIN    activity       all_act
            ON  run_act.activity_id = all_act.id
        WHERE   all_act.status != 'CLOSED'
    """, (app_session_id,))
    return data[0][0]

async def create_activities(golem, db, payload, expected_cnt, max_concurrent=2):
    chain = await get_chain(golem, db, payload)
    tasks = []

    semaphore = asyncio.BoundedSemaphore(max_concurrent)
    chain_lock = asyncio.Lock()
    while True:
        await semaphore.acquire()

        running_activity_cnt = await get_running_activity_cnt(db, golem.app_session_id)
        running_task_cnt = len([task for task in tasks if not task.done()])

        if running_activity_cnt + running_task_cnt < expected_cnt:
            tasks.append(asyncio.create_task(get_new_activity(chain_lock, chain, semaphore)))
        else:
            semaphore.release()
            await asyncio.sleep(1)
