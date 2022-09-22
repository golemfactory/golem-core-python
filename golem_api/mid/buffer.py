import asyncio
from typing import AsyncIterator, Awaitable, List, Optional, TypeVar

X = TypeVar("X")


class Buffer:
    def __init__(self, size=1):
        self.size = size

        self._semaphore = asyncio.BoundedSemaphore(size)
        self._result_queue: asyncio.Queue[X] = asyncio.Queue()
        self._tasks: List[asyncio.Task] = []
        self._main_task: Optional[asyncio.Task] = None
        self._in_stream: Optional[AsyncIterator[Awaitable[X]]] = None
        self._in_stream_exhausted = False

    async def __call__(self, in_stream: AsyncIterator[Awaitable[X]]) -> AsyncIterator[X]:
        self._in_stream = in_stream
        self._main_task = asyncio.create_task(self._process_in_stream())

        while not (
            self._in_stream_exhausted
            and self._result_queue.empty()
            and all(task.done() for task in self._tasks)
        ):
            yield await self._result_queue.get()
            self._semaphore.release()

    async def _process_in_stream(self) -> None:
        while True:
            await self._semaphore.acquire()
            try:
                in_val = await self._in_stream.__anext__()
            except StopAsyncIteration:
                self._in_stream_exhausted = True
                return
            task = asyncio.create_task(self._process_single_value(in_val))
            self._tasks.append(task)

    async def _process_single_value(self, in_val) -> None:
        #   TODO: not awaitable? print something like "useless buffer" and put
        #   result in queue without awaiting
        self._result_queue.put_nowait(await in_val)
