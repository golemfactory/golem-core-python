import asyncio
import inspect
from typing import AsyncIterator, Awaitable, List, Union

from golem_api.low.activity import Activity


class ActivityPool:
    """Collects activities. Yields activities that are currently idle.

    Sample usage::

        from golem_api import GolemNode
        from golem_api.mid import Chain, Buffer, Map, ActivityPool
        from golem_api.commands import Run

        async def say_hi(activity):
            batch = await activity.execute_commands(Run(f"echo -n 'Hi, this is {activity}'"))
            await batch.wait(10)
            return batch.events[0].stdout

        async with GolemNode() as golem:
            async def activity_stream():
                #   This assumes we have some ready activities with known ids
                yield golem.activity(first_activity_id)
                yield golem.activity(second_activity_id)

            async for result in Chain(
                activity_stream(),
                ActivityPool(max_size=2),
                Map(say_hi),
                Buffer(size=2),
            ):
                print(result)
                #   Forever prints greetings from activities

    Caveats:
        *   Assumes input stream never ends (this is a TODO)
        *   :any:`Activity` is again considered idle (and thus eligible for yielding) after a single batch
            was executed. This has two important consequences:

            *   :any:`Activity` will not be yielded again if it was not used at all
            *   Yielded :any:`Activity` should not be used for more than a single batch
        *   Whenever an :any:`Activity` known to the ActivityPool is destroyed it will be replaced
            with a new :any:`Activity` from the source stream

    """

    def __init__(self, max_size: int = 1):
        """
        :param max_size: Maximal size of the ActivityPool. Actual size can be lower - it grows only when
            ActivityPool is asked for an activity and there is no idle activity that can be returned
            immediately.
        """
        self.max_size = max_size

        self._idle_activities: List[Activity] = []
        self._activity_manager_tasks: List[asyncio.Task] = []

    def full(self) -> bool:
        running_managers = [task for task in self._activity_manager_tasks if not task.done()]
        return len(running_managers) >= self.max_size

    async def __call__(
        self, activity_stream: AsyncIterator[Union[Activity, Awaitable[Activity]]]
    ) -> AsyncIterator[Union[Activity, Awaitable[Activity]]]:
        """
        :param activity_stream: Stream of either :any:`Activity` or Awaitable[Activity].
            It is assumed all obtained activities start idle.
        """
        while True:
            if not self._idle_activities and not self.full():
                future_activity = self._as_awaitable(await activity_stream.__anext__())
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
        await activity.wait_destroyed()
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
            await activity.wait_busy()
            if activity in self._idle_activities:
                self._idle_activities.remove(activity)
            await activity.wait_idle()

    def _as_awaitable(self, in_: Union[Activity, Awaitable[Activity]]) -> Awaitable[Activity]:
        if inspect.isawaitable(in_):
            return in_
        else:
            fut: asyncio.Future[Activity] = asyncio.Future()
            assert isinstance(in_, Activity)  # mypy
            fut.set_result(in_)
            return fut
