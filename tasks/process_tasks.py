import asyncio

from golem_core.mid import (
    Chain, Map, Zip, Buffer,
)

def get_process_task(locked_activities):
    async def process_task(activity, task):
        try:
            print(f"Task start: {activity}")
            result = await task(activity)
            return result
        finally:
            locked_activities.remove(activity.id)
    return process_task

async def get_next_activity_id(db, locked_activities, app_session_id):
    data = await db.select("""
        SELECT  activity_id
        FROM    tasks.activities(%(app_session_id)s) run_act
        JOIN    activity                             all_act
            ON  run_act.activity_id = all_act.id
        WHERE   all_act.status = 'READY'
            AND NOT activity_id = ANY(%(locked_activities)s)
        LIMIT   1
    """, {"app_session_id": app_session_id, "locked_activities": locked_activities})
    if data:
        activity_id = data[0][0]
        if activity_id in locked_activities:
            #   Rare case where we performed two selects concurrently
            #   (I'm not 100% sure if this is possible at all)
            return None
        locked_activities.append(activity_id)
        return activity_id
    return None

async def process_tasks(golem, db, get_tasks, max_concurrent=2) -> None:
    locked_activities = ['aaa']

    async def task_stream():
        for task in get_tasks():
            yield task

    async def activity_stream():
        while True:
            next_activity_id = await get_next_activity_id(db, locked_activities, golem.app_session_id)
            if next_activity_id is not None:
                yield golem.activity(next_activity_id)
            else:
                await asyncio.sleep(0.1)

    async for _ in Chain(
        activity_stream(),
        Zip(task_stream()),
        Map(get_process_task(locked_activities)),
        Buffer(size=max_concurrent),
    ):
        pass
