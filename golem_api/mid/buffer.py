import asyncio
import inspect
from typing import AsyncIterator, Awaitable, Generic, List, Optional, TypeVar, Union

DataType = TypeVar("DataType")


class Buffer(Generic[DataType]):
    """
    Process concurrently multiple elements from an async stream of awaitables.

    Sample usage::

        async def awaitable_foo():
            await asyncio.sleep(1)
            return "foo"

        async def awaitable_bar():
            await asyncio.sleep(1)
            return "bar"

        async def stream():
            yield awaitable_foo()
            yield awaitable_bar()

        #   Prints "foo" after a second and "bar" after another second
        async for x in Buffer()(stream()):
            print(x)

        #   Prints "foo" and "bar" after a single second
        async for x in Buffer(size=2)(stream()):
            print(x)

    Caveats:

    *   Assumes input stream never ends (this is a TODO)

    """

    def __init__(self, size: int = 1):
        """
        :param size: How many elements of the input stream will be concurrently awaited.
            Default size=1 is identical to a single `await` statement.
            In most Golem-specific scenarios buffer size will correspond to things like
            "how many agreements are negotiated at the same time", so usually the higher the size:

            * The faster we'll be able to create and utilize resources
            * The higher chance for "useless" resources (e.g. we might be creating multiple agreements
              even when there is only a single task left)
            * The higher workload for the local machine (more asyncio tasks) and yagna (more requests)
        """
        self.size = size

        self._semaphore = asyncio.BoundedSemaphore(size)
        self._result_queue: asyncio.Queue[DataType] = asyncio.Queue()
        self._tasks: List[asyncio.Task] = []
        self._main_task: Optional[asyncio.Task] = None
        self._in_stream_exhausted = False

    async def __call__(self, in_stream: AsyncIterator[Union[DataType, Awaitable[DataType]]]) -> AsyncIterator[DataType]:
        """
        :param in_stream: A stream of awaitables.
        """
        self._main_task = asyncio.create_task(self._process_in_stream(in_stream))

        while not (
            self._in_stream_exhausted
            and self._result_queue.empty()
            and all(task.done() for task in self._tasks)
        ):
            yield await self._result_queue.get()
            self._semaphore.release()

    async def _process_in_stream(self, in_stream: AsyncIterator[Union[DataType, Awaitable[DataType]]]) -> None:
        while True:
            await self._semaphore.acquire()
            try:
                in_val = await in_stream.__anext__()
            except StopAsyncIteration:
                self._in_stream_exhausted = True
                return
            task = asyncio.create_task(self._process_single_value(in_val))
            self._tasks.append(task)

    async def _process_single_value(self, in_val: Union[DataType, Awaitable[DataType]]) -> None:
        awaited: DataType
        if inspect.isawaitable(in_val):
            try:
                awaited = await in_val
            except Exception as e:
                print(e)
                self._semaphore.release()
                return
        else:
            #   NOTE: Buffer is useful only with awaitables, so this scenario doesn't make much sense.
            #         But maybe stream sometimes returns awaitables and sometimes already awaited values?
            awaited = in_val  # type: ignore
        self._result_queue.put_nowait(awaited)
