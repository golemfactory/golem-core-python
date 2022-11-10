import asyncio
from typing import Generic, Iterable, List, TypeVar

TaskData = TypeVar("TaskData")


class TaskDataStream(Generic[TaskData]):
    """Wrapper for any iterable (TODO: or async iterable) with a convenient repeating interface.

    Sample usage::

        task_cnt = 10
        data = iter(range(task_cnt))
        task_data_stream = TaskDataStream(data)

        returned = 0
        processed = 0
        async for task_data in task_data_stream:
            processed += 1
            if random.random() > 0.6:
                #   Repeat a task
                print("REPEAT")
                task_data_stream.put(task_data)
                continue

            returned += 1
            if task_data_stream.in_stream_empty and returned == task_data_stream.task_cnt:
                break

        assert returned == task_cnt
        print(processed)
    """
    #   TODO: https://github.com/golemfactory/golem-api-python/issues/16
    def __init__(self, in_stream: Iterable[TaskData]):
        self.in_stream = iter(in_stream)

        self.task_cnt = 0
        self.in_stream_empty = False

        self._queue: asyncio.Queue[TaskData] = asyncio.Queue()
        self._in_stream_next()

    def _in_stream_next(self) -> None:
        try:
            next_val = next(self.in_stream)
        except StopIteration:
            self.in_stream_empty = True
            return
        self.task_cnt += 1
        self.put(next_val)

    def put(self, value: TaskData) -> None:
        self._queue.put_nowait(value)

    def __aiter__(self) -> "TaskDataStream":
        return self

    async def __anext__(self) -> TaskData:
        #   Q: Why this way? Looks weird?
        #   A: The goal is to have self.in_stream_empty == True once we return the last element from the in_stream.
        #      This is an important part of the interface.
        #
        #   Note that we don't want to ever raise StopAsyncIteration - a call to `put` can
        #   happen at any time.
        val = await self._queue.get()
        if self._queue.empty() and not self.in_stream_empty:
            self._in_stream_next()
        return val

    def all_remaining_tasks(self) -> List[TaskData]:
        #   TODO: this method is a shortcut for the current simplified RedundanceManager.
        #   It should disappear once we add support for async iterators.
        current_queue_tasks = []
        while not self._queue.empty():
            current_queue_tasks.append(self._queue.get_nowait())
        new_tasks = list(self.in_stream)
        self.task_cnt += len(new_tasks)
        self.in_stream_empty = True
        return current_queue_tasks + new_tasks
