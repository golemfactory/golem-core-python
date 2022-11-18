import asyncio
from typing import List, Optional, Union, TYPE_CHECKING

from ipaddress import ip_network, IPv4Address, IPv6Address, IPv4Network, IPv6Network
from ya_net import RequestorApi, models

from golem_api.events import ResourceClosed
from .api_call_wrapper import api_call_wrapper
from .exceptions import NetworkFull
from .resource import Resource
from .resource_internals import _NULL

IpAddress = Union[IPv4Address, IPv6Address]
IpNetwork = Union[IPv4Network, IPv6Network]

if TYPE_CHECKING:
    from golem_api.golem_node import GolemNode


class Network(Resource[RequestorApi, models.Network, _NULL, _NULL, _NULL]):
    def __init__(self, golem_node: "GolemNode", id_: str, data: models.Network):
        super().__init__(golem_node, id_, data)

        self._create_node_lock = asyncio.Lock()
        self._ip_network: IpNetwork = ip_network(data.ip, strict=False)
        self._all_ips = [str(ip) for ip in self._ip_network.hosts()]

        self._requestor_ips = []
        self._nodes = {}

    @property
    def network_address(self):
        return str(self._ip_network.network_address)

    @classmethod
    @api_call_wrapper()
    async def create(cls, golem_node: "GolemNode", ip: str, mask: Optional[str], gateway: Optional[str]) -> "Network":
        api = cls._get_api(golem_node)
        in_data = models.Network(ip=ip, mask=mask, gateway=gateway)
        created_data = await api.create_network(in_data)
        return cls(golem_node, created_data.id, created_data)

    @api_call_wrapper()
    async def remove(self):
        await self.api.remove_network(self.id)
        self.node.event_bus.emit(ResourceClosed(self))

    @api_call_wrapper()
    async def create_node(self, provider_id: str, node_ip: Optional[str] = None) -> str:
        #   Q: Why is there no `Node` class?
        #   A: Mostly because yagna nodes don't have proper IDs (they are just provider_ids), and this
        #      is strongly against the current golem_api object model (e.g. what if we want to have the
        #      same provider in muliple networks? Nodes would share the same id, but are totally diferent objects).
        #      We could bypass this by having some internal ids (e.g. network_id-provider_id, or just uuid),
        #      but this would not be pretty and there's no gain from having a Node object either way.
        #      This might change in the future.
        async with self._create_node_lock:
            if node_ip is None:
                node_ip = self._next_free_ip()

            data = models.Node(id=provider_id, ip=node_ip)
            await self.api.add_node(self.id, data)

            self._nodes[node_ip] = provider_id
            return node_ip

    @api_call_wrapper()
    async def refresh_nodes(self):
        tasks = []
        for ip, provider_id in self._nodes.items():
            data = models.Node(id=provider_id, ip=ip)
            tasks.append(self.api.add_node(self.id, data))
        await asyncio.gather(*tasks)

    def deploy_args(self, ip: str):
        return {
            "net": [
                {
                    "id": self.id,
                    "ip": self.network_address,
                    "mask": self.data.mask,
                    "nodeIp": ip,
                    "nodes": self._nodes,
                }
            ]
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

    def _next_free_ip(self) -> IpAddress:
        try:
            return next(ip for ip in self._all_ips if ip not in self._current_ips)
        except StopIteration:
            raise NetworkFull(self)

    @classmethod
    def _id_field_name(cls) -> str:
        #   All ya_client models have id fields that include model name, e.g.
        #   Allocation.allocation_id, Demand.demand_id etc, but we have Network.id
        return "id"
