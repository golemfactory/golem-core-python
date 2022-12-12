import asyncio

from golem_core.mid import (
    Chain, Map, Zip, Buffer,
)

class TaskExecutor:
    def __init__(self, golem, db, *, get_tasks, max_concurrent):
        self.golem = golem
        self.db = db
        self.get_tasks = get_tasks
        self.max_concurrent = max_concurrent

        self.locked_activities = []

    async def run(self):
        async for _ in Chain(
            self._activity_stream(),
            Zip(self._task_stream()),
            Map(self._process_task),
            Buffer(size=self.max_concurrent),
        ):
            pass

    async def _task_stream(self):
        for task in self.get_tasks():
            yield task

    async def _activity_stream(self):
        while True:
            next_activity_id = await self._get_next_activity_id()
            if next_activity_id is not None:
                yield self.golem.activity(next_activity_id)
            else:
                await asyncio.sleep(0.1)

    async def _process_task(self, activity, task):
        try:
            print(f"Task start: {activity}")
            result = await task(activity)
            return result
        finally:
            self.locked_activities.remove(activity.id)

    async def _get_next_activity_id(self):
        locked_activities = self.locked_activities

        data = await self.db.select("""
            SELECT  activity_id
            FROM    tasks.activities(%(app_session_id)s) run_act
            JOIN    activity                             all_act
                ON  run_act.activity_id = all_act.id
            WHERE   all_act.status = 'READY'
                AND NOT activity_id = ANY(%(locked_activities)s)
            LIMIT   1
        """, {"app_session_id": self.golem.app_session_id, "locked_activities": locked_activities})
        if data:
            activity_id = data[0][0]
            if activity_id in locked_activities:
                #   Rare case where we performed two selects concurrently
                #   (I'm not 100% sure if this is possible at all)
                return None
            locked_activities.append(activity_id)
            return activity_id
        return None
