import asyncio
from typing import AsyncIterator, Awaitable, List

from golem_api.low.activity import Activity


class ActivityPool:
    def __init__(self):
        self._idle_activities: List[Activity] = []
        self._activity_manager_tasks: List[asyncio.Task] = []

    async def __call__(self, activity_stream: AsyncIterator[Awaitable[Activity]]) -> AsyncIterator[Awaitable[Activity]]:
        while True:
            if self._idle_activities:
                activity = self._idle_activities.pop(0)

                #   Compatibility - always yields awaitable
                future_activity = asyncio.Future()
                future_activity.set_result(activity)
                yield future_activity
            else:
                future_activity = await activity_stream.__anext__()
                manager_task = asyncio.create_task(self._manage_activity(future_activity))
                self._activity_manager_tasks.append(manager_task)
                yield future_activity

    async def _manage_activity(self, future_activity: Awaitable[Activity]):
        activity = await future_activity
        while True:
            self._idle_activities.append(activity)
            await activity.busy_event.wait()
            if activity in self._idle_activities:
                self._idle_activities.remove(activity)
            await activity.idle_event.wait()
