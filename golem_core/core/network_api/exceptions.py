from typing import TYPE_CHECKING

from golem_core.core.exceptions import BaseCoreException

if TYPE_CHECKING:
    from golem_core.core.network_api.resources import Network


class BaseNetworkApiException(BaseCoreException):
    pass


class NetworkFull(BaseNetworkApiException):
    """Raised when we need a new free ip but there are no free ips left in the :any:`Network`."""

    def __init__(self, network: "Network"):
        self._network = network
        super().__init__(f"{network} is full - there are no free ips left")

    @property
    def network(self) -> "Network":
        return self._network
