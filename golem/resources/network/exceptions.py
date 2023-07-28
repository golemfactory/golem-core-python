from typing import TYPE_CHECKING

from golem.resources.exceptions import ResourceException

if TYPE_CHECKING:
    from golem.resources.network.network import Network


class NetworkException(ResourceException):
    pass


class NetworkFull(NetworkException):
    """Raised when we need a new free ip but there are no free ips left in the :any:`Network`."""

    def __init__(self, network: "Network"):
        self._network = network
        super().__init__(f"{network} is full - there are no free ips left")

    @property
    def network(self) -> "Network":
        return self._network
