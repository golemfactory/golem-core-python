from typing import TYPE_CHECKING

from golem.resources.events import NewResource, ResourceEvent

if TYPE_CHECKING:
    from golem.resources.pooling_batch.pooling_batch import PoolingBatch  # noqa


class NewPoolingBatch(NewResource["PoolingBatch"]):
    pass


class BatchFinished(ResourceEvent["PoolingBatch"]):
    """Emitted when the execution of a :any:`PoolingBatch` finishes.

    The same event is emitted for successful and failed batches.
    """
