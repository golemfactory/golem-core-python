import asyncio
import logging
from typing import Dict
from urllib.parse import urlparse

from golem.managers.base import NetworkManager
from golem.node import GolemNode
from golem.resources import DeployArgsType, Network, NewAgreement
from golem.utils.logging import trace_span

logger = logging.getLogger(__name__)


class SingleNetworkManager(NetworkManager):
    def __init__(self, golem: GolemNode, ip: str) -> None:
        self._golem = golem
        self._ip = ip
        self._nodes: Dict[str, str] = {}

    @trace_span()
    async def start(self):
        self._network = await Network.create(self._golem, self._ip, None, None)
        await self._network.add_requestor_ip(None)
        self._golem.add_autoclose_resource(self._network)

        await self._golem.event_bus.on(NewAgreement, self._add_provider_to_network)

    @trace_span()
    async def get_node_id(self, provider_id: str) -> str:
        while True:
            node_ip = self._nodes.get(provider_id)
            if node_ip:
                return node_ip

            # TODO: get rid of sleep
            await asyncio.sleep(0.1)

    @trace_span(show_arguments=True, show_results=True)
    async def get_deploy_args(self, provider_id: str) -> DeployArgsType:
        node_ip = await self.get_node_id(provider_id)
        return self._network.deploy_args(node_ip)

    @trace_span(show_arguments=True, show_results=True)
    async def get_provider_uri(self, provider_id: str, protocol: str = "http") -> str:
        node_ip = await self.get_node_id(provider_id)
        url = self._network.node._api_config.net_url
        net_api_ws = urlparse(url)._replace(scheme=protocol).geturl()
        connection_uri = f"{net_api_ws}/net/{self._network.id}/tcp/{node_ip}/22"
        return connection_uri

    @trace_span(show_arguments=True)
    async def _add_provider_to_network(self, event: NewAgreement):
        await event.resource.get_data()
        provider_id = event.resource.data.offer.provider_id
        assert provider_id is not None  # TODO handle this case better
        logger.info(f"Adding provider {provider_id} to network")
        self._nodes[provider_id] = await self._network.create_node(provider_id)
