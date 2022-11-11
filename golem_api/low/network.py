from typing import Optional, TYPE_CHECKING

from ya_net import RequestorApi, models

from golem_api.events import ResourceClosed
from .api_call_wrapper import api_call_wrapper
from .resource import Resource
from .resource_internals import _NULL

if TYPE_CHECKING:
    from golem_api.golem_node import GolemNode


class Network(Resource[RequestorApi, models.Network, _NULL, models.Node, _NULL]):
    @classmethod
    @api_call_wrapper()
    async def create(cls, node: "GolemNode", ip: str, mask: Optional[str], gateway: Optional[str]) -> "Network":
        api = cls._get_api(node)
        in_data = models.Network(ip=ip, mask=mask, gateway=gateway)
        created_data = await api.create_network(in_data)
        return cls(node, created_data.id, created_data)

    @api_call_wrapper()
    async def remove(self):
        await self.api.remove_network(self.id)
        self.node.event_bus.emit(ResourceClosed(self))

    @classmethod
    def _id_field_name(cls) -> str:
        #   All ya_client models have id fields that include model name, e.g.
        #   Allocation.allocatio_id, Demand.demand_id etc, but we have Network.id and Node.id
        return "id"
