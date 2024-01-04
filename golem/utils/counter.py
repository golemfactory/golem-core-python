import asyncio


class AsyncCounter:
    def __init__(self, start_with=0):
        self._counter = start_with
        self._pending_count = 0
        self._condition = asyncio.Condition()
        self._finished = asyncio.Event()

        self._finished.set()

    async def increment(self, value=1) -> None:
        async with self._condition:
            self._counter += value

            self._condition.notify_all()
            self._finished.clear()

    async def decrement(self, value=1) -> None:
        async with self._condition:
            await self._condition.wait_for(lambda: value < self._counter)

            self._counter -= value

    async def reset(self, value=0) -> None:
        self._counter = value
        self._pending_count = 0
        self._finished.set()

    def task_done(self):
        if self._pending_count <= 0:
            raise ValueError('task_done() called too many times!')

        self._pending_count -= 1

        if not self._pending_count:
            self._finished.set()

    async def join(self) -> None:
        await self._finished.wait()

    def pending_count(self) -> int:
        return self._pending_count
