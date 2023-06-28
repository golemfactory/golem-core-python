from typing import TYPE_CHECKING

from golem.resources.events import NewResource, ResourceClosed, ResourceDataChanged

if TYPE_CHECKING:
    from golem.resources.allocation.allocation import Allocation  # noqa


class NewAllocation(NewResource["Allocation"]):
    pass


class AllocationDataChanged(ResourceDataChanged["Allocation"]):
    pass


class AllocationClosed(ResourceClosed["Allocation"]):
    pass
