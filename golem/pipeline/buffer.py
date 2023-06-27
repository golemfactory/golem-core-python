import asyncio
import inspect
from typing import AsyncIterator, Awaitable, Generic, List, TypeVar, Union

from golem.pipeline.exceptions import InputStreamExhausted

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

    """

    def __init__(self, size: int = 1):
        """Init Buffer.

        :param size: How many elements of the input stream will be concurrently awaited.
            Default size=1 is identical to a single `await` statement.
            In most Golem-specific scenarios buffer size will correspond to things like
            "how many agreements are negotiated at the same time", so usually the higher the size:

            * The faster we'll be able to create and utilize resources
            * The higher chance for "useless" resources (e.g. we might be creating multiple
              agreements even when there is only a single task left)
            * The higher workload for the local machine (more asyncio tasks) and yagna
              (more requests)
        """
        self.size = size

    async def __call__(
        self, in_stream: AsyncIterator[Union[DataType, Awaitable[DataType]]]
    ) -> AsyncIterator[DataType]:
        """Call Buffer.

        :param in_stream: A stream of awaitables.
        """
        self._tasks: List[asyncio.Task] = []
        self._in_stream_exhausted = False
        self._result_queue: asyncio.Queue[DataType] = asyncio.Queue()
        self._main_task = asyncio.create_task(self._process_in_stream(in_stream))
        self._semaphore = asyncio.BoundedSemaphore(self.size)

        stop_task = asyncio.create_task(self._wait_until_empty())

        while True:
            get_result_task = asyncio.create_task(self._result_queue.get())
            await asyncio.wait((get_result_task, stop_task), return_when=asyncio.FIRST_COMPLETED)
            if stop_task.done():
                get_result_task.cancel()
                break
            else:
                yield get_result_task.result()
                self._semaphore.release()

    async def _process_in_stream(
        self, in_stream: AsyncIterator[Union[DataType, Awaitable[DataType]]]
    ) -> None:
        while True:
            await self._semaphore.acquire()
            try:
                in_val = await in_stream.__anext__()
            except StopAsyncIteration:
                self._semaphore.release()
                self._in_stream_exhausted = True
                return
            task = asyncio.create_task(self._process_single_value(in_val))
            self._tasks.append(task)

    async def _process_single_value(self, in_val: Union[DataType, Awaitable[DataType]]) -> None:
        awaited: DataType
        if inspect.isawaitable(in_val):
            try:
                awaited = await in_val
            except InputStreamExhausted:
                self._main_task.cancel()
                self._semaphore.release()
                self._in_stream_exhausted = True
                return
            except Exception as e:
                self._semaphore.release()
                #   TODO https://github.com/golemfactory/golem-core-python/issues/27
                print("Exception in Buffer", e)
                return
        else:
            #   NOTE: Buffer is useful only with awaitables, so this scenario doesn't make much
            #         sense. But maybe stream sometimes returns awaitables and sometimes already
            #         awaited values?
            awaited = in_val  # type: ignore

        self._result_queue.put_nowait(awaited)

    async def _wait_until_empty(self) -> None:
        while True:
            if (
                self._in_stream_exhausted
                and self._result_queue.empty()
                and all(task.done() for task in self._tasks)
            ):
                return
            else:
                await asyncio.sleep(0.01)
