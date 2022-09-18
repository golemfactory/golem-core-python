import asyncio
import inspect
from typing import AsyncIterator, Awaitable, Callable, Iterable, List, TypeVar, Union

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

        self._task_data_stream_exhausted = False
        self._result_queue: asyncio.Queue[TaskResult] = asyncio.Queue()

        #   TODO: remove finished tasks?
        self._current_tasks: List[asyncio.Task] = []
        self._main_task: asyncio.Task = asyncio.create_task(self._main_task())

    async def results(self) -> AsyncIterator[TaskResult]:
        while not (self._task_data_stream_exhausted and all(task.done() for task in self._current_tasks)):
            result = await self._result_queue.get()
            yield result

    async def _main_task(self):
        for task_data in self.task_data:
            self._create_task(task_data)
        self._task_data_stream_exhausted = True

    def _create_task(self, task_data: TaskData) -> None:
        task = asyncio.create_task(self._process_single_task(task_data))
        self._current_tasks.append(task)

    async def _process_single_task(self, task_data: TaskData):
        activity = await self._get_activity()
        try:
            result = await self.execute_task(activity, task_data)
            self._result_queue.put_nowait(result)
        except Exception as e:
            print("EXCEPTION", e)
            self._create_task(task_data)

    async def _get_activity(self) -> Activity:
        activity = await self.activity_stream.__anext__()
        if inspect.isawaitable(activity):
            activity = await activity
        return activity  # type: ignore
