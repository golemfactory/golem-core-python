class NewAllocation(NewResource["Allocation"]):
    pass


class AllocationDataChanged(ResourceDataChanged["Allocation"]):
    pass


class AllocationClosed(ResourceClosed["Allocation"]):
    pass
