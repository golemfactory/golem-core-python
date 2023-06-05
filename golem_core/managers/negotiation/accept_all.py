import asyncio
import logging
from abc import ABC, abstractmethod
from copy import deepcopy
from datetime import datetime, timezone
from typing import AsyncIterator, Awaitable, Callable, List, Optional

from golem_core.core.golem_node.golem_node import DEFAULT_EXPIRATION_TIMEOUT, SUBNET, GolemNode
from golem_core.core.market_api import Demand, DemandBuilder, Payload, Proposal
from golem_core.core.market_api.resources.demand.demand_offer_base import defaults as dobm_defaults
from golem_core.core.payment_api import Allocation
from golem_core.managers.base import NegotiationManager, ManagerException

logger = logging.getLogger(__name__)


class IgnoreProposal(Exception):
    pass

class NegotiationPlugin(ABC):
    @abstractmethod
    async def __call__(self, demand_builder: DemandBuilder, proposal: Proposal) -> DemandBuilder:
        ...


class AcceptAllNegotiationManager(NegotiationManager):
    def __init__(
        self,
        golem: GolemNode,
        get_allocation: Callable[[], Awaitable[Allocation]],
        payload: Payload,
    ) -> None:
        self._golem = golem
        self._get_allocation = get_allocation
        self._payload = payload

        self._negotiation_loop_task: Optional[asyncio.Task] = None
        self._plugins: List[NegotiationPlugin] = []
        self._eligible_proposals: asyncio.Queue[Proposal] = asyncio.Queue()

    def register_plugin(self, plugin: NegotiationPlugin):
        self._plugins.append(plugin)

    def unregister_plugin(self, plugin: NegotiationPlugin):
        self._plugins.remove(plugin)

    async def get_proposal(self) -> Proposal:
        logger.debug("Getting proposal...")

        proposal = await self._eligible_proposals.get()

        logger.debug(f"Getting proposal done with `{proposal}`")

        return proposal

    async def start(self) -> None:
        logger.debug("Starting negotiations...")

        if self.is_negotiation_started():
            message = "Negotiation is already started!"
            logger.debug(f"Starting negotiations failed with `{message}`")
            raise ManagerException(message)

        self._negotiation_loop_task = asyncio.create_task(self._negotiation_loop(payload))

        logger.debug("Starting negotiations done")

    async def stop(self) -> None:
        logger.debug("Stopping negotiations...")

        if not self.is_negotiation_started():
            message = "Negotiation is already stopped!"
            logger.debug(f"Stopping negotiations failed with `{message}`")
            raise ManagerException(message)

        self._negotiation_loop_task.cancel()
        self._negotiation_loop_task = None

        logger.debug("Stopping negotiations done")

    def is_negotiation_started(self) -> bool:
        return self._negotiation_loop_task is not None

    async def _negotiation_loop(self, payload: Payload) -> None:
        allocation = await self._get_allocation()
        demand = await self._build_demand(allocation, payload)

        try:
            async for proposal in self._negotiate(demand):
                await self._eligible_proposals.put(proposal)
        finally:
            await demand.unsubscribe()

    async def _build_demand(self, allocation: Allocation, payload: Payload) -> Demand:
        logger.debug("Creating demand...")

        demand_builder = DemandBuilder()

        await demand_builder.add(
            dobm_defaults.Activity(
                expiration=datetime.now(timezone.utc) + DEFAULT_EXPIRATION_TIMEOUT,
                multi_activity=True,
            )
        )
        await demand_builder.add(dobm_defaults.NodeInfo(subnet_tag=SUBNET))

        await demand_builder.add(payload)

        (
            allocation_properties,
            allocation_constraints,
        ) = await allocation.demand_properties_constraints()
        demand_builder.add_constraints(*allocation_constraints)
        demand_builder.add_properties({p.key: p.value for p in allocation_properties})

        demand = await demand_builder.create_demand(self._golem)
        demand.start_collecting_events()

        logger.debug(f"Creating demand done with `{demand}`")

        return demand

    async def _negotiate(self, demand: Demand) -> AsyncIterator[Proposal]:
        async for initial in demand.initial_proposals():
            logger.debug(f"Negotiating initial proposal `{initial}`...")

            try:
                demand_proposal = await initial.respond()
            except Exception as e:
                logger.debug(f"Negotiating initial proposal `{initial}` failed with `{e}`")
                continue

            try:
                offer_proposal = await demand_proposal.responses().__anext__()
            except StopAsyncIteration:
                continue

            logger.debug(f"Negotiating initial proposal `{initial}` done")

            yield offer_proposal

    async def _negotiate_with_plugins(self, offer_proposal: Proposal) -> Optional[Proposal]:
        while True:
            original_demand_builder = DemandBuilder.from_proposal(offer_proposal)
            demand_builder = deepcopy(original_demand_builder)

            try:
                for plugin in self._plugins:
                    demand_builder = await plugin(demand_builder, offer_proposal)
            except IgnoreProposal:
                return None

            if offer_proposal.initial or demand_builder != original_demand_builder:
                demand_proposal = await offer_proposal.respond(demand_builder.properties, demand_builder.constraints)
                offer_proposal = await demand_proposal.responses().__anext__()
                continue

            return offer_proposal
