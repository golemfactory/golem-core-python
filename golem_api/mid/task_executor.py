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
        max_concurrent: int = 0,
    ):
        self.execute_task = execute_task
        self.activity_stream = activity_stream
        self.task_data = task_data

        self._task_data_stream_exhausted = False
        self._result_queue: asyncio.Queue[TaskResult] = asyncio.Queue()

        self._semaphore = None
        if max_concurrent > 0:
            self._semaphore = asyncio.BoundedSemaphore(max_concurrent)

        #   TODO: remove finished tasks?
        self._current_tasks: List[asyncio.Task] = []
        self._main_task: asyncio.Task = asyncio.create_task(self._process_task_data_stream())

    async def results(self) -> AsyncIterator[TaskResult]:
        while not (
            self._task_data_stream_exhausted
            and self._result_queue.empty()
            and all(task.done() for task in self._current_tasks)
        ):
            result = await self._result_queue.get()
            yield result  # type: ignore  # mypy, why?

    async def _process_task_data_stream(self) -> None:
        for task_data in self.task_data:
            if self._semaphore is not None:
                await self._semaphore.acquire()
            self._create_task(task_data)
        self._task_data_stream_exhausted = True

    def _create_task(self, task_data: TaskData) -> None:
        task = asyncio.create_task(self._process_single_task(task_data))
        self._current_tasks.append(task)

    async def _process_single_task(self, task_data: TaskData) -> None:
        activity = await self._get_activity()
        try:
            result = await self.execute_task(activity, task_data)
            self._result_queue.put_nowait(result)
            if self._semaphore is not None:
                self._semaphore.release()
        except Exception as e:
            print(f"EXCEPTION ON {activity} for task {task_data}: {e}")
            await activity.destroy()
            self._create_task(task_data)

    async def _get_activity(self) -> Activity:
        activity = await self.activity_stream.__anext__()
        if inspect.isawaitable(activity):
            activity = await activity
        return activity  # type: ignore
