from typing import TYPE_CHECKING

from golem_core.core.resources import ResourceEvent


if TYPE_CHECKING:
    from golem_core.core.activity_api.resources import PoolingBatch


class BatchFinished(ResourceEvent):
    """Emitted when the execution of a :any:`PoolingBatch` finishes.

    The same event is emitted for successful and failed batches."""
    def __init__(self, resource: "PoolingBatch"):
        super().__init__(resource)
