import asyncio
from typing import Generic, Optional, TypeVar

from golem.utils.asyncio.tasks import ensure_cancelled_many

TQueueItem = TypeVar("TQueueItem")


class ErrorReportingQueue(asyncio.Queue, Generic[TQueueItem]):
    """Asyncio Queue that enables exceptions to be passed to consumers from the feeding code."""

    def __init__(self, *args, **kwargs):
        self._error: Optional[BaseException] = None
        self._error_event: asyncio.Event = asyncio.Event()

        super().__init__(*args, **kwargs)

    def get_nowait(self) -> TQueueItem:
        """Perform a regular `get_nowait` if there are items in the queue.

        Otherwise, if an exception had been signalled, raise the exception.
        """
        if self.empty() and self._error:
            raise self._error
        return super().get_nowait()

    async def get(self) -> TQueueItem:
        """Perform a regular, waiting `get` but raise an exception if happens while waiting.

        If there had been items in the queue,
        they will first be returned before an exception is raised.
        """

        error_task = asyncio.create_task(self._error_event.wait())
        get_task = asyncio.create_task(super().get())
        done, pending = await asyncio.wait(
            [error_task, get_task], return_when=asyncio.FIRST_COMPLETED
        )

        await ensure_cancelled_many(pending)

        if get_task in done:
            return await get_task

        assert self._error
        raise self._error

    async def put(self, item: TQueueItem):
        await super().put(item)

    def put_nowait(self, item: TQueueItem):
        super().put_nowait(item)

    def set_exception(self, exc: BaseException):
        """Set the exception, causing subsequent get calls to fail with an exception."""
        self._error = exc
        self._error_event.set()

    def reset_exception(self):
        """Reset the exception in case the condition that caused it originally had been resolved."""
        self._error = None
        self._error_event.clear()
