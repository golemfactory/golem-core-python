from abc import ABC, abstractmethod
import asyncio
from typing import AsyncIterator, Generic, List, Optional, TypeVar


InType = TypeVar("InType")
OutType = TypeVar("OutType")


class BufferedPipe(ABC, Generic[InType, OutType]):
    def __init__(self, *, buffer_size: int = 0):
        """A generic base class for all buffered Chain elements.

        :param buffer_size: (number_of_current_negotiations + number_of_values_ready_to_return) will always
            equal this number (except when the initial stream was exhausted, when it will be lower).
        """
        self.main_task: Optional[asyncio.Task] = None
        self.tasks: List[asyncio.Task] = []
        self.queue: asyncio.Queue[OutType] = asyncio.Queue()

        #   Acquire to start negotiations. Release:
        #   A) after failed negotiations
        #   B) when yielding a value
        #   --> we always have (current_negotiations + values_ready_to_yield) == buffer_size
        self.semaphore = asyncio.BoundedSemaphore(buffer_size)

    async def __call__(self, in_stream: AsyncIterator[InType]) -> AsyncIterator[OutType]:
        self._in_stream_exhausted = False
        self.main_task = asyncio.create_task(self._process_in_stream(in_stream))

        while not self.queue.empty() or not self._in_stream_exhausted or self._has_running_tasks:
            # TODO: How do we close this stream?
            #       Also: was there any reason to implement in the commented way?
            # try:
            #     out_val = self.queue.get_nowait()
            # except asyncio.QueueEmpty:
            #     await asyncio.sleep(0.1)
            #     continue
            yield await self.queue.get()
            self.semaphore.release()

    @property
    def _has_running_tasks(self) -> bool:
        return not all(task.done() for task in self.tasks)

    async def _process_in_stream(self, in_stream: AsyncIterator[InType]) -> None:
        #   Q: Why not `async for in_val in in_stream`?
        #   A: Because we should request a new item from the in_stream only after semaphore is acquired.
        #      There are two main reasons behind this:
        #      * yielding a value might require some work from the in_stream
        #      * value yielded now might be better than the one that would have been yielded before,
        #        (e.g. a better proposal), so we want to get the value as late as possible
        while True:
            await self.semaphore.acquire()
            try:
                in_val = await in_stream.__anext__()
            except StopAsyncIteration:
                break
            self.tasks.append(asyncio.create_task(self._process_single_item_wrapper(in_val)))

        self._in_stream_exhausted = True

    async def _process_single_item_wrapper(self, in_val: InType) -> None:
        # print(f"START {in_val}")
        try:
            out_val = await self._process_single_item(in_val)
            if out_val is not None:
                self.queue.put_nowait(out_val)
            else:
                self.semaphore.release()
        except Exception:
            self.semaphore.release()
        # print(f"STOP {in_val}")

    @abstractmethod
    async def _process_single_item(self, in_val: InType) -> Optional[OutType]:
        raise NotImplementedError
