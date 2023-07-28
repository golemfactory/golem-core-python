from typing import TYPE_CHECKING

from golem.resources.events import NewResource, ResourceClosed, ResourceDataChanged

if TYPE_CHECKING:
    from golem.resources.network.network import Network  # noqa


class NewNetwork(NewResource["Network"]):
    pass


class NetworkDataChanged(ResourceDataChanged["Network"]):
    pass


class NetworkClosed(ResourceClosed["Network"]):
    pass
