import asyncio


class SingleUseSemaphore:
    """Class similar to `asyncio.Semaphore` but with more limited count of `.acquire()` calls and\
    exposed counters."""

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
        """Return True if there are no more "charges" left in semaphore."""

        return not self._value

    async def acquire(self) -> None:
        """Decrease "charges" counter and increase pending count, or await until there any\
        "charges"."""

        async with self._condition:
            await self._condition.wait_for(lambda: self._value)

            self._value -= 1
            self._pending += 1

    def release(self) -> None:
        """Decrease pending count."""

        if self._pending <= 0:
            raise RuntimeError("Release called too many times!")

        self._pending -= 1

        if self.locked():
            self.finished.set()

    async def increase(self, value: int) -> None:
        """Add given "charges" amount."""

        async with self._condition:
            self._value += value
            self.finished.clear()
            self._condition.notify(value)

    def get_count(self) -> int:
        """Return "charges" count."""

        return self._value

    def get_count_with_pending(self) -> int:
        """Return sum of "charges" and pending count."""

        return self.get_count() + self.get_pending_count()

    def get_pending_count(self) -> int:
        """Return pending count."""

        return self._pending

    def reset(self) -> None:
        """Reset "charges" amount to zero."""

        self._value = 0
