from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from golem_api.low.activity import PoolingBatch


class ResourceNotFound(Exception):
    """Emitted on an attempt to interact with a resource that doesn't exist.

    Example::

        async with GolemNode() as golem:
            agreement_id = "".join(["a" for x in range(64)])
            agreement = golem.agreement(agreement_id)
            try:
                await agreement.get_data()
            except ResourceNotFound as e:
                print(f"Agreement with id {e.resource.id} doesn't exist")


        """
    def __init__(self, name: str, id_: str):
        self.name = name
        self.id = id_

        msg = f"{name}({id_}) doesn't exist"
        super().__init__(msg)


class NoMatchingAccount(Exception):
    def __init__(self, network: str, driver: str):
        #   NOTE: we don't really care about this sort of compatibility, but this is
        #         a message developers are used to so maybe it's worth reusing
        from yapapi.engine import NoPaymentAccountError
        msg = str(NoPaymentAccountError(driver, network))
        super().__init__(msg)


class BatchTimeoutError(Exception):
    def __init__(self, batch: "PoolingBatch", timeout: float):
        self.batch = batch
        self.timeout = timeout

        msg = f"{batch} did not finish in {timeout} seconds"
        super().__init__(msg)


class BatchError(Exception):
    """Unspecified exception related to the execution of a batch."""
    def __init__(self, batch: "PoolingBatch", msg: Optional[str] = None):
        self.batch = batch

        if msg is None:
            event = batch.events[-1]
            msg = f"{batch} failed on command {event.index}: {event.message}"

        super().__init__(msg)


class CommandFailed(BatchError):
    """Exception raised when awaiting for a result of the command that failed."""
    def __init__(self, batch: "PoolingBatch"):
        event = batch.events[-1]
        msg = f"Command {event.index} in batch {batch} failed: {event.message}"
        super().__init__(batch, msg)


class CommandCancelled(BatchError):
    """Exception raised when awaiting for a result of command that was not executed at all."""
    def __init__(self, batch: "PoolingBatch"):
        event = batch.events[-1]
        msg = (
            f"Command was cancelled because {batch} failed before the command was executed. "
            f"Details: command {event.index} failed with {event.message}"
        )
        super().__init__(batch, msg)
