from typing import TYPE_CHECKING

from golem.resources.events import NewResource, ResourceClosed, ResourceDataChanged

if TYPE_CHECKING:
    from golem.resources.demand.demand import Demand  # noqa


class NewDemand(NewResource["Demand"]):
    pass


class DemandDataChanged(ResourceDataChanged["Demand"]):
    pass


class DemandClosed(ResourceClosed["Demand"]):
    pass
