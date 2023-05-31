from typing import TYPE_CHECKING

from golem_core.core.resources import NewResource, ResourceClosed, ResourceDataChanged

if TYPE_CHECKING:
    pass


class NewNetwork(NewResource["Network"]):
    pass


class NetworkDataChanged(ResourceDataChanged["Network"]):
    pass


class NetworkClosed(ResourceClosed["Network"]):
    pass
