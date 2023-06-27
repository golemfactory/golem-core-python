class NewPoolingBatch(NewResource["PoolingBatch"]):
    pass


class BatchFinished(ResourceEvent["PoolingBatch"]):
    """Emitted when the execution of a :any:`PoolingBatch` finishes.

    The same event is emitted for successful and failed batches.
    """
