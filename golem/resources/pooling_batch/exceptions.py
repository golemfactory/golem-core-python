from typing import TYPE_CHECKING, Optional

from golem.resources.exceptions import ResourceException

if TYPE_CHECKING:
    from golem.resources.pooling_batch.pooling_batch import PoolingBatch


class PoolingBatchException(ResourceException):
    pass


class BatchError(PoolingBatchException):
    """Unspecified exception related to the execution of a batch."""

    def __init__(self, batch: "PoolingBatch", msg: Optional[str] = None):
        self._batch = batch

        if msg is None:
            if batch.events:
                event = batch.events[-1]
                msg = f"{batch} failed on command {event.index}: {event.message}"
            else:
                msg = f"{batch} failed to collect any events"

        super().__init__(msg)

    @property
    def batch(self) -> "PoolingBatch":
        return self._batch


class CommandFailed(BatchError):
    """Raised when awaiting for a result of a command that failed."""

    def __init__(self, batch: "PoolingBatch"):
        event = batch.events[-1]
        msg = f"Command {event.index} in batch {batch} failed: {event.message}"
        super().__init__(batch, msg)


class CommandCancelled(BatchError):
    """Raised when awaiting for a result of a command that was not executed at all because a \
    previous command failed."""

    def __init__(self, batch: "PoolingBatch"):
        event = batch.events[-1]
        msg = (
            f"Command was cancelled because {batch} failed before the command was executed. "
            f"Details: command {event.index} failed with {event.message}"
        )
        super().__init__(batch, msg)


class BatchTimeoutError(PoolingBatchException):
    """Raised in :any:`PoolingBatch.wait()` when the batch execution timed out."""

    def __init__(self, batch: "PoolingBatch", timeout: float):
        self._batch = batch
        self._timeout = timeout

        msg = f"{batch} did not finish in {timeout} seconds"
        super().__init__(msg)

    @property
    def batch(self) -> "PoolingBatch":
        return self._batch

    @property
    def timeout(self) -> float:
        return self._timeout
