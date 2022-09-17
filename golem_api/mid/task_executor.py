import inspect
from typing import AsyncIterator, Awaitable, Callable, Iterable, TypeVar, Union

from golem_api.low import Activity

TaskData = TypeVar("TaskData")
TaskResult = TypeVar("TaskResult")


class TaskExecutor:
    def __init__(
        self,
        execute_task: Callable[[Activity, TaskData], Awaitable[TaskResult]],
        activity_stream: Union[AsyncIterator[Activity], AsyncIterator[Awaitable[Activity]]],
        task_data: Iterable[TaskData],
    ):
        self.execute_task = execute_task
        self.activity_stream = activity_stream
        self.task_data = task_data

    async def results(self) -> AsyncIterator[TaskResult]:
        for task_data in self.task_data:
            activity = await self._get_activity()
            result = await self.execute_task(activity, task_data)
            yield result  # type: ignore  # mypy, why?

    async def _get_activity(self) -> Activity:
        activity = await self.activity_stream.__anext__()
        if inspect.isawaitable(activity):
            activity = await activity
        return activity  # type: ignore
