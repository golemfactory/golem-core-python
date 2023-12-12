import asyncio
from typing import Generic, Optional, TypeVar

QueueItem = TypeVar("QueueItem")


class ErrorReportingQueue(asyncio.Queue, Generic[QueueItem]):
    """Asyncio Queue that enables exceptions to be passed to consumers from the feeding code."""

    _error: Optional[BaseException]
    _error_event: asyncio.Event

    def __init__(self, *args, **kwargs):
        self._error = None
        self._error_event = asyncio.Event()
        super().__init__(*args, **kwargs)

    def get_nowait(self) -> QueueItem:
        """Perform a regular `get_nowait` if there are items in the queue.

        Otherwise, if an exception had been signalled, raise the exception.
        """
        if self.empty() and self._error:
            raise self._error
        return super().get_nowait()

    async def get(self) -> QueueItem:
        """Perform a regular, waiting `get` but raise an exception if happens while waiting.

        If there had been items in the queue, they will first be returned before an exception is raised.
        """

        error_task = asyncio.create_task(self._error_event.wait())
        get_task = asyncio.create_task(super().get())
        done, pending = await asyncio.wait(
            [error_task, get_task], return_when=asyncio.FIRST_COMPLETED
        )

        [t.cancel() for t in pending]

        if get_task in done:
            return await get_task

        raise self._error

    async def put(self, item: QueueItem):
        await super().put(item)

    def put_nowait(self, item: QueueItem):
        super().put_nowait(item)

    def set_exception(self, exc: BaseException):
        """Set the exception, causing subsequent get calls to fail with an exception."""
        self._error = exc
        self._error_event.set()

    def reset_exception(self):
        """Reset the exception in case the condition that caused it originally had been resolved."""
        self._error = None
        self._error_event.clear()
