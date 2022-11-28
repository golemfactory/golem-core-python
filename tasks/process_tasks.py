import asyncio

from golem_api.mid import (
    Chain, Map, Zip, Buffer,
)

def get_process_task(locked_activities):
    async def process_task(activity, task):
        try:
            return await task(activity)
        finally:
            locked_activities.remove(activity.id)
    return process_task

async def get_next_activity_id(db, locked_activities, app_session_id):
    data = await db.select("""
        SELECT  activity_id
        FROM    tasks.activities(%s) run_act
        JOIN    activity             all_act
            ON  run_act.activity_id = all_act.id
        WHERE   all_act.status = 'READY'
        LIMIT   1
    """, (app_session_id, ))
    if data:
        activity_id = data[0][0]
        locked_activities.append(activity_id)
        return activity_id
    return None

async def process_tasks(golem, db, get_tasks) -> None:
    locked_activities = []

    async def task_stream():
        for task in get_tasks():
            yield task

    async def activity_stream():
        while True:
            next_activity_id = await get_next_activity_id(db, locked_activities, golem.app_session_id)
            if next_activity_id is not None:
                yield golem.activity(next_activity_id)
            else:
                await asyncio.sleep(1)

    async for _ in Chain(
        activity_stream(),
        Zip(task_stream()),
        Map(get_process_task(locked_activities)),
        Buffer(size=2),
    ):
        pass
