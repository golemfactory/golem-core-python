import asyncio
import random

from golem_api import commands


class ActivityPool:
    def __init__(self):
        self._activity_queue = asyncio.Queue()

    def consume_activities(self, activity_chain):
        async def consumer():
            async for activity in activity_chain:
                self._activity_queue.put_nowait(activity)

        return asyncio.create_task(consumer())

    def execute_in_pool(self, func):
        async def execute(*args, **kwargs):
            try:
                activity = await self._activity_queue.get()
                return await func(activity, *args, **kwargs)
            finally:
                self._activity_queue.put_nowait(activity)

        return execute


class ExecuteTaskFailed(Exception):
    def __init__(self, activity, task_data):
        self.activity = activity
        self.task_data = task_data
        super().__init__(f"Ooops, failed to process task {task_data} on {activity}")


async def execute_task(activity, task_data):
    print(f"Executing task {task_data} on {activity}")

    batch = await activity.execute_commands(
        commands.Run(f"echo -n $(({task_data} * 7))"),
    )
    await batch.wait()

    if random.random() > 0.7:
        raise ExecuteTaskFailed(activity, task_data)

    return task_data, batch.events[0].stdout
