import asyncio
from typing import Generic, Iterable, List, TypeVar

TaskData = TypeVar("TaskData")


class TaskDataStream(Generic[TaskData]):
    #   TODO: in_stream could be AsyncIterable as well
    def __init__(self, in_stream: Iterable[TaskData], queue_min_size: int = 10):
        self.in_stream = iter(in_stream)
        self.queue_min_size = queue_min_size

        self.task_cnt = 0
        self.in_stream_empty = False

        self._queue = asyncio.Queue()
        self._task = asyncio.create_task(self._keep_queue_min_size())

    async def _keep_queue_min_size(self):
        while True:
            if self._queue.qsize() < self.queue_min_size:
                try:
                    next_val = next(self.in_stream)
                except StopIteration:
                    self.in_stream_empty = True
                    break
                self.task_cnt += 1
                self.put(next_val)
            else:
                await asyncio.sleep(0.1)

    def put(self, value: TaskData) -> None:
        self._queue.put_nowait(value)

    def __aiter__(self) -> "TaskDataStream":
        return self

    async def __anext__(self) -> TaskData:
        return await self._queue.get()

    def all_remaining_tasks(self) -> List[TaskData]:
        current_queue_tasks = []
        while not self._queue.empty():
            current_queue_tasks.append(self._queue.get_nowait())
        new_tasks = list(self.in_stream)
        self.task_cnt += len(new_tasks)
        self.in_stream_empty = True
        return current_queue_tasks + new_tasks
