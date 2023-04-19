import asyncio
import inspect
from typing import AsyncIterator, Awaitable, List, Union

from golem_core.core.activity_api.resources import Activity

from golem_core.pipeline.exceptions import InputStreamExhausted


class ActivityPool:
    """Collects activities. Yields activities that are currently idle.

    Sample usage::

        from golem_core import GolemNode
        from golem_core.pipeline import Chain, Buffer, Map, ActivityPool
        from golem_core.commands import Run

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

        self._idle_activities: asyncio.Queue[Activity] = asyncio.Queue()
        self._activity_manager_tasks: List[asyncio.Task] = []
        self._in_stream_lock = asyncio.Lock()
        self._in_stream_empty = False

    def full(self) -> bool:
        running_managers = [task for task in self._activity_manager_tasks if not task.done()]
        return len(running_managers) >= self.max_size

    async def __call__(
        self, activity_stream: AsyncIterator[Union[Activity, Awaitable[Activity]]]
    ) -> AsyncIterator[Awaitable[Activity]]:
        """
        :param activity_stream: Stream of either :any:`Activity` or Awaitable[Activity].
            It is assumed all obtained activities start idle.
        """
        while True:
            yield self._get_next_idle_activity(activity_stream)

    def _create_manager_task(self, future_activity: Awaitable[Activity]) -> None:
        #   Create an activity manager task
        manager_task = asyncio.create_task(self._manage_activity(future_activity))
        self._activity_manager_tasks.append(manager_task)

        #   Create a separate task that will stop the manager task when activity is destroyed
        asyncio.create_task(self._activity_destroyed_cleanup(manager_task, future_activity))

    async def _activity_destroyed_cleanup(
        self, manager_task: asyncio.Task, future_activity: Awaitable[Activity]
    ) -> None:
        try:
            activity = await future_activity
        except InputStreamExhausted:
            return

        await activity.wait_destroyed()
        manager_task.cancel()

    async def _get_next_idle_activity(
        self, activity_stream: AsyncIterator[Union[Activity, Awaitable[Activity]]]
    ) -> Activity:
        while True:
            if not self._in_stream_empty and self._idle_activities.empty() and not self.full():
                async with self._in_stream_lock:
                    try:
                        maybe_future_activity = await activity_stream.__anext__()
                    except StopAsyncIteration:
                        self._in_stream_empty = True
                        continue

                future_activity = self._as_awaitable(maybe_future_activity)
                self._create_manager_task(future_activity)

            activity = await self._idle_activities.get()
            if not activity.destroyed:
                return activity

    async def _manage_activity(self, future_activity: Awaitable[Activity]) -> None:
        try:
            activity = await future_activity
        except InputStreamExhausted:
            return

        while True:
            self._idle_activities.put_nowait(activity)
            await activity.wait_busy()
            await activity.wait_idle()

    def _as_awaitable(self, in_: Union[Activity, Awaitable[Activity]]) -> Awaitable[Activity]:
        if inspect.isawaitable(in_):
            return in_
        else:
            fut: asyncio.Future[Activity] = asyncio.Future()
            assert isinstance(in_, Activity)  # mypy
            fut.set_result(in_)
            return fut
