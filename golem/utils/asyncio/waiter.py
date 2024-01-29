import asyncio
import collections
from typing import Callable, Deque


class Waiter:
    """Class similar to `asyncio.Event` but valueless and with notify interface similar to \
    `asyncio.Condition`.

    Note: Developed to support `golem.utils.asyncio.buffer`, but finally not used.
    """

    def __init__(self) -> None:
        self._waiters: Deque[asyncio.Future] = collections.deque()
        self._loop = asyncio.get_event_loop()

    async def wait_for(self, predicate: Callable[[], bool]) -> None:
        """Check if predicate is true and return immediately, or await until it becomes true."""

        result = predicate()

        while not result:
            await self._wait()
            result = predicate()

            if not result:
                # as last `._wait()` call woken us up but predicate is still false, lets give a
                # chance another `.wait_for()` pending call.
                self._notify_first()

    def _notify_first(self) -> None:
        try:
            first_waiter = self._waiters[0]
        except IndexError:
            return

        if not first_waiter.done():
            first_waiter.set_result(None)

    async def _wait(self) -> None:
        future = self._loop.create_future()
        self._waiters.append(future)
        try:
            await future
        finally:
            self._waiters.remove(future)

    def notify(self, count=1) -> None:
        """Notify given amount of `.wait_for()` calls to check its predicates."""

        notified = 0
        for waiter in self._waiters:
            if count <= notified:
                break

            if not waiter.done():
                waiter.set_result(None)
                notified += 1
