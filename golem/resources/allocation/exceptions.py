from golem.resources.exceptions import ResourceException


class AllocationException(ResourceException):
    pass


class NoMatchingAccount(AllocationException):
    """Raised when a new :any:`Allocation` is created for a (network, driver) pair without \
    matching `yagna` account."""

    def __init__(self, network: str, driver: str):
        self._network = network
        self._driver = driver

        #   NOTE: we don't really care about this sort of compatibility, but this is
        #         a message developers are used to so maybe it's worth reusing
        msg = f"No payment account available for driver `{driver}` and network `{network}`"
        super().__init__(msg)

    @property
    def network(self) -> str:
        return self._network

    @property
    def driver(self) -> str:
        return self._driver
