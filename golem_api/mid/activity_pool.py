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
                self._create_manager_task(future_activity)
            yield self._get_next_idle_activity()

    def _create_manager_task(self, future_activity: Awaitable[Activity]) -> None:
        #   Create an activity manager task
        manager_task = asyncio.create_task(self._manage_activity(future_activity))
        self._activity_manager_tasks.append(manager_task)

        #   Create a separate task that will stop the manager task
        asyncio.create_task(self._activity_destroyed_cleanup(manager_task, future_activity))

    async def _activity_destroyed_cleanup(
        self, manager_task: asyncio.Task, future_activity: Awaitable[Activity]
    ) -> None:
        activity = await future_activity
        await activity.destroyed_event.wait()
        manager_task.cancel()
        if activity in self._idle_activities:
            self._idle_activities.remove(activity)

    async def _get_next_idle_activity(self) -> Activity:
        while True:
            if self._idle_activities:
                return self._idle_activities.pop(0)
            else:
                await asyncio.sleep(0.1)

    async def _manage_activity(self, future_activity: Awaitable[Activity]) -> None:
        activity = await future_activity
        while True:
            self._idle_activities.append(activity)
            await activity.busy_event.wait()
            if activity in self._idle_activities:
                self._idle_activities.remove(activity)
            await activity.idle_event.wait()
