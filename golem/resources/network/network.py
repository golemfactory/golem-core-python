import asyncio
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, ip_network
from typing import TYPE_CHECKING, Dict, List, Optional, TypedDict, Union

from ya_net import RequestorApi, models

from golem.resources.base import _NULL, Resource, api_call_wrapper
from golem.resources.network.events import NetworkClosed, NewNetwork
from golem.resources.network.exceptions import NetworkFull

if TYPE_CHECKING:
    from golem.node import GolemNode

IpAddress = Union[IPv4Address, IPv6Address]
IpNetwork = Union[IPv4Network, IPv6Network]


class DeployArgsType(TypedDict):
    id: str
    ip: str
    mask: Optional[str]
    nodeIp: str
    nodes: Dict[str, str]


class Network(Resource[RequestorApi, models.Network, _NULL, _NULL, _NULL]):
    """A single vpn on the Golem Network.

    Sample usage::

        activity: Activity
        network = await golem.create_network()

        provider_id = activity.parent.parent.data.issuer_id
        ip = await network.create_node(provider_id)

        deploy_args = {"net": [network.deploy_args(ip)]}
        await activity.execute_commands(commands.Deploy(deploy_args))

        #   activity can now be accessed from other nodes in the network

    """

    def __init__(self, golem_node: "GolemNode", id_: str, data: models.Network):
        super().__init__(golem_node, id_, data)
        asyncio.create_task(golem_node.event_bus.emit(NewNetwork(self)))

        self._create_node_lock = asyncio.Lock()
        self._ip_network: IpNetwork = ip_network(data.ip, strict=False)
        self._all_ips = [str(ip) for ip in self._ip_network.hosts()]

        self._requestor_ips: List[str] = []
        self._nodes: Dict[str, str] = {}

    @property
    def network_address(self) -> str:
        return str(self._ip_network.network_address)

    @classmethod
    @api_call_wrapper()
    async def create(
        cls, golem_node: "GolemNode", ip: str, mask: Optional[str], gateway: Optional[str]
    ) -> "Network":
        api = cls._get_api(golem_node)
        in_data = models.Network(ip=ip, mask=mask, gateway=gateway)
        created_data = await api.create_network(in_data)
        return cls(golem_node, created_data.id, created_data)

    @api_call_wrapper(ignore=[404])
    async def remove(self) -> None:
        """Remove the network."""
        await self.api.remove_network(self.id)
        await self.node.event_bus.emit(NetworkClosed(self))

    @api_call_wrapper()
    async def create_node(self, provider_id: str, node_ip: Optional[str] = None) -> str:
        """Add a node to the network.

        :param provider_id: ID of the provider who hosts the :any:`Activity` that will
            be connected to the new node.
        :param node_ip: IP of the node in the network, by default next free IP will be used.
        :return: IP of the node in the network.
        """
        #   Q: Why is there no `Node` class?
        #   A: Mostly because yagna nodes don't have proper IDs (they are just provider_ids), and
        #      this is strongly against the current golem object model (e.g. what if we want to
        #      have the same provider in muliple networks? Nodes would share the same id, but are
        #      totally diferent objects). We could bypass this by having some internal ids
        #      (e.g. network_id-provider_id, or just uuid), but this would not be pretty and there's
        #      no gain from having a Node object either way. This might change in the future.
        async with self._create_node_lock:
            if node_ip is None:
                node_ip = self._next_free_ip()
            assert node_ip is not None  # mypy, why?

            data = models.Node(id=provider_id, ip=node_ip)  # type: ignore  # mypy, why?
            await self.api.add_node(self.id, data)

            self._nodes[node_ip] = provider_id
            return node_ip

    @api_call_wrapper()
    async def refresh_nodes(self) -> None:
        """Propagates the information about created nodes to the network.

        TODO: more precise explanation maybe?
        """
        tasks = []
        for ip, provider_id in self._nodes.items():
            data = models.Node(id=provider_id, ip=ip)  # type: ignore  # mypy, why?
            tasks.append(self.api.add_node(self.id, data))
        await asyncio.gather(*tasks)

    def deploy_args(self, ip: str) -> DeployArgsType:
        """Get a data structure that should be passed to :any:`Deploy`.

        This makes an :any:`Activity` a part of the network.

        :param ip: IP of the previously created network node.

        Sample usage::

            deploy_args = {"net": [network.deploy_args(ip)]}
            await activity.execute_commands(commands.Deploy(deploy_args))

        """
        return {
            "id": self.id,
            "ip": self.network_address,
            "mask": self.data.mask,
            "nodeIp": ip,
            "nodes": self._nodes,
        }

    @api_call_wrapper()
    async def add_requestor_ip(self, ip: Optional[str]) -> None:
        async with self._create_node_lock:
            if ip is None:
                ip = self._next_free_ip()
            self._requestor_ips.append(ip)
        await self.api.add_address(self.id, models.Address(ip))

    @property
    def _current_ips(self) -> List[str]:
        return self._requestor_ips + list(self._nodes)

    def _next_free_ip(self) -> str:
        try:
            return next(ip for ip in self._all_ips if ip not in self._current_ips)
        except StopIteration:
            raise NetworkFull(self)

    @classmethod
    def _id_field_name(cls) -> str:
        #   All ya_client models have id fields that include model name, e.g.
        #   Allocation.allocation_id, Demand.demand_id etc, but we have Network.id
        return "id"
