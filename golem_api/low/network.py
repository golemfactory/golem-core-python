import asyncio
from typing import Optional, TYPE_CHECKING

from ya_net import RequestorApi, models

from golem_api.events import ResourceClosed
from .api_call_wrapper import api_call_wrapper
from .resource import Resource
from .resource_internals import _NULL

if TYPE_CHECKING:
    from golem_api.golem_node import GolemNode


class Network(Resource[RequestorApi, models.Network, _NULL, "Node", _NULL]):
    def __init__(self, golem_node: "GolemNode", id_: str, data: models.Network):
        super().__init__(golem_node, id_, data)

        self._create_node_lock = asyncio.Lock()

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
            node = await Node.create(golem_node, node_id, node_ip)
            return
            self.add_child(node)

            return node

    def _next_free_ip(self) -> str:
        return "123.123"

    @classmethod
    def _id_field_name(cls) -> str:
        #   All ya_client models have id fields that include model name, e.g.
        #   Allocation.allocatio_id, Demand.demand_id etc, but we have Network.id and Node.id
        return "id"


class Node(Resource[RequestorApi, models.Node, Network, _NULL, _NULL]):
    @classmethod
    @api_call_wrapper()
    async def create(cls, golem_node: "GolemNode", id_, ip):
        print("CREATE", id_, ip)
