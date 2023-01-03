import asyncio

from golem_core.mid import (
    Chain, Map, Zip, Buffer,
)
from golem_core.high.task_data_stream import TaskDataStream

class TaskExecutor:
    def __init__(self, golem, db, *, get_tasks, max_concurrent):
        self.golem = golem
        self.db = db
        self.task_stream = TaskDataStream(get_tasks(self.db.run_id))
        self.get_tasks = get_tasks
        self.max_concurrent = max_concurrent

        self.locked_activities = []

        self._stopping = False

    async def run(self):
        try:
            async for _ in Chain(
                self._activity_stream(),
                Zip(self.task_stream),
                Map(self._process_task),
                Buffer(size=self.max_concurrent),
            ):
                pass
        except asyncio.CancelledError:
            self._stopping = True
            raise

    async def _activity_stream(self):
        while not self._stopping:
            next_activity_id = await self._get_next_activity_id()
            if next_activity_id is not None:
                yield self.golem.activity(next_activity_id)
            else:
                await asyncio.sleep(0.1)

    async def _process_task(self, activity, task):
        try:
            result = await task(activity)
            return result
        except Exception:
            self.task_stream.put(task)
            await self.db.close_activity(activity, 'task failed')
        finally:
            self.locked_activities.remove(activity.id)

    async def _get_next_activity_id(self):
        locked_activities = self.locked_activities

        data = await self.db.select("""
            SELECT  activity_id
            FROM    activities(%(run_id)s) run_act
            JOIN    activity               all_act
                ON  run_act.activity_id = all_act.id
            WHERE   all_act.status = 'READY'
                AND NOT activity_id = ANY(%(locked_activities)s)
            ORDER BY random()
            LIMIT   1
        """, {"locked_activities": locked_activities})
        if data:
            activity_id = data[0][0]
            if activity_id in locked_activities:
                #   Rare case where we performed two selects concurrently
                #   (I'm not 100% sure if this is possible at all)
                return None
            locked_activities.append(activity_id)
            return activity_id
        return None
