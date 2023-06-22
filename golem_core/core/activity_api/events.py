from golem_core.core.resources import (
    NewResource,
    ResourceClosed,
    ResourceDataChanged,
    ResourceEvent,
)


class NewActivity(NewResource["Activity"]):
    pass


class ActivityDataChanged(ResourceDataChanged["Activity"]):
    pass


class ActivityClosed(ResourceClosed["Activity"]):
    pass


class NewPoolingBatch(NewResource["PoolingBatch"]):
    pass


class BatchFinished(ResourceEvent["PoolingBatch"]):
    """Emitted when the execution of a :any:`PoolingBatch` finishes.

    The same event is emitted for successful and failed batches.
    """
