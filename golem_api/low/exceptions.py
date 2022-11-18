from typing import Optional, TYPE_CHECKING

from yapapi.engine import NoPaymentAccountError

if TYPE_CHECKING:
    from golem_api.low.resource import Resource
    from golem_api.low.activity import PoolingBatch
    from golem_api.low.network import Network


class ResourceNotFound(Exception):
    """Raised on an attempt to interact with a resource that doesn't exist.

    Example::

        async with GolemNode() as golem:
            agreement_id = "".join(["a" for x in range(64)])
            agreement = golem.agreement(agreement_id)
            try:
                await agreement.get_data()
            except ResourceNotFound as e:
                print(f"Agreement with id {e.resource.id} doesn't exist")


        """
    def __init__(self, resource: "Resource"):
        self._resource = resource

        msg = f"{resource} doesn't exist"
        super().__init__(msg)

    @property
    def resource(self) -> "Resource":
        """Resource that caused the exception."""
        return self._resource


class NoMatchingAccount(Exception):
    """Raised when a new :any:`Allocation` is created for a (network, driver) pair without matching `yagna` account."""
    def __init__(self, network: str, driver: str):
        self._network = network
        self._driver = driver

        #   NOTE: we don't really care about this sort of compatibility, but this is
        #         a message developers are used to so maybe it's worth reusing
        msg = str(NoPaymentAccountError(driver, network))
        super().__init__(msg)

    @property
    def network(self) -> str:
        return self._network

    @property
    def driver(self) -> str:
        return self._driver


class BatchTimeoutError(Exception):
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


class BatchError(Exception):
    """Unspecified exception related to the execution of a batch."""
    def __init__(self, batch: "PoolingBatch", msg: Optional[str] = None):
        self._batch = batch

        if msg is None:
            event = batch.events[-1]
            msg = f"{batch} failed on command {event.index}: {event.message}"

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
    """Raised when awaiting for a result of a command that was not executed at all because a previous command failed."""
    def __init__(self, batch: "PoolingBatch"):
        event = batch.events[-1]
        msg = (
            f"Command was cancelled because {batch} failed before the command was executed. "
            f"Details: command {event.index} failed with {event.message}"
        )
        super().__init__(batch, msg)


class NetworkFull(Exception):
    """Raised when we need a new free ip but there are no free ips left in the :any:`Network`."""
    def __init__(self, network: "Network"):
        self._network = network
        super().__init__(f"{network} is full - there are no free ips left")

    @property
    def network(self) -> "Network":
        return self._network
