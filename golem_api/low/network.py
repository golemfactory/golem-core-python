import asyncio
from typing import List, Optional, Union, TYPE_CHECKING

from ipaddress import ip_network, IPv4Address, IPv6Address, IPv4Network, IPv6Network
from ya_net import RequestorApi, models

from golem_api.events import ResourceClosed
from .api_call_wrapper import api_call_wrapper
from .resource import Resource
from .resource_internals import _NULL

IpAddress = Union[IPv4Address, IPv6Address]
IpNetwork = Union[IPv4Network, IPv6Network]

if TYPE_CHECKING:
    from golem_api.golem_node import GolemNode


class Network(Resource[RequestorApi, models.Network, _NULL, "Node", _NULL]):
    def __init__(self, golem_node: "GolemNode", id_: str, data: models.Network):
        super().__init__(golem_node, id_, data)

        self._create_node_lock = asyncio.Lock()
        self._ip_network: IpNetwork = ip_network(data.ip, strict=False)
        self._requestor_ips = []
        self._all_ips = [str(ip) for ip in self._ip_network.hosts()]

    @property
    def nodes(self) -> List["Node"]:
        return self.children

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

    async def create_node(self, node_id: str, node_ip: Optional[str] = None) -> "Node":
        async with self._create_node_lock:
            if node_ip is None:
                node_ip = self._next_free_ip()

            golem_node = self.node
            node = await Node.create(golem_node, self.id, node_id, node_ip)
            self.add_child(node)

            return node

    async def refresh_nodes(self):
        tasks = []
        for node in self.nodes:
            data = models.Node(id=node.id, ip=node.data.ip)
            tasks.append(self.api.add_node(self.id, data))
        await asyncio.gather(*tasks)

    @api_call_wrapper()
    async def add_requestor_ip(self, ip: Optional[str]) -> None:
        async with self._create_node_lock:
            if ip is None:
                ip = self._next_free_ip()
            self._requestor_ips.append(ip)
        await self.api.add_address(self.id, models.Address(ip))

    @property
    def _current_ips(self) -> List[IpAddress]:
        #   TODO: this ignores possible removed nodes - once an IP was assigned,
        #         it is always "current_ip". This might not be perfect.
        return self._requestor_ips + [node.data.ip for node in self.children]

    def _next_free_ip(self) -> IpAddress:
        try:
            return next(ip for ip in self._all_ips if ip not in self._current_ips)
        except StopIteration:
            raise Exception(f"{self} is full - there are no free ips left")

    @classmethod
    def _id_field_name(cls) -> str:
        #   All ya_client models have id fields that include model name, e.g.
        #   Allocation.allocatio_id, Demand.demand_id etc, but we have Network.id and Node.id
        return "id"


class Node(Resource[RequestorApi, models.Node, Network, _NULL, _NULL]):
    @classmethod
    @api_call_wrapper()
    async def create(cls, golem_node: "GolemNode", network_id, node_id, ip):
        api = cls._get_api(golem_node)
        data = models.Node(id=node_id, ip=ip)
        await api.add_node(network_id, data)
        return Node(golem_node, node_id, data)

    def deploy_args(self):
        network = self.parent
        return {
            "net": [
                {
                    "id": network.id,
                    "ip": "192.168.0.0",
                    "mask": network.data.mask,
                    "nodeIp": self.data.ip,
                    "nodes": {node.data.ip: node.id for node in network.nodes},
                }
            ]
        }
