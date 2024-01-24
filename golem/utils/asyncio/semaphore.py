import asyncio


class SingleUseSemaphore:
    def __init__(self, value=0):
        if value < 0:
            raise ValueError("Initial value must be greater or equal to zero!")

        self._value = value

        self._pending = 0
        self._condition = asyncio.Condition()

        self.finished = asyncio.Event()
        if self.locked():
            self.finished.set()

    async def __aenter__(self):
        await self.acquire()

    async def __aexit__(self, exc_type, exc, tb):
        self.release()

    def locked(self) -> bool:
        return not self._value

    async def acquire(self) -> None:
        async with self._condition:
            await self._condition.wait_for(lambda: self._value)

            self._value -= 1
            self._pending += 1

    def release(self) -> None:
        if self._pending <= 0:
            raise RuntimeError("Release called too many times!")

        self._pending -= 1

        if self.locked():
            self.finished.set()

    async def increase(self, value: int) -> None:
        async with self._condition:
            self._value += value
            self.finished.clear()
            self._condition.notify(value)

    def get_count(self) -> int:
        return self._value

    def get_count_with_pending(self) -> int:
        return self.get_count() + self.get_pending_count()

    def get_pending_count(self) -> int:
        return self._pending

    def reset(self) -> None:
        self._value = 0
        self.finished.set()
