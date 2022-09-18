import asyncio
from typing import AsyncIterator, Awaitable, List

from golem_api.low.activity import Activity


class ActivityPool:
    def __init__(self, max_size: int = 0):
        self.max_size = max_size

        self._idle_activities: List[Activity] = []
        self._activity_manager_tasks: List[asyncio.Task] = []

    def full(self) -> bool:
        if self.max_size == 0:
            return False
        running_managers = [task for task in self._activity_manager_tasks if not task.done()]
        return len(running_managers) >= self.max_size

    async def __call__(self, activity_stream: AsyncIterator[Awaitable[Activity]]) -> AsyncIterator[Awaitable[Activity]]:
        while True:
            if not self._idle_activities and not self.full():
                future_activity = await activity_stream.__anext__()
                manager_task = asyncio.create_task(self._manage_activity(future_activity))
                self._activity_manager_tasks.append(manager_task)
            yield self._get_next_idle_activity()

    async def _get_next_idle_activity(self) -> Activity:
        while True:
            if self._idle_activities:
                return self._idle_activities.pop(0)
            else:
                await asyncio.sleep(0.1)

    async def _manage_activity(self, future_activity: Awaitable[Activity]):
        activity = await future_activity
        while not activity.terminated:
            self._idle_activities.append(activity)
            await activity.busy_event.wait()
            if activity in self._idle_activities:
                self._idle_activities.remove(activity)
            await activity.idle_event.wait()
