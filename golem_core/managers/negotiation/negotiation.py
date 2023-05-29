import asyncio
import logging
from datetime import datetime, timezone
from typing import AsyncIterator, Awaitable, Callable, List

from golem_core.core.golem_node.golem_node import DEFAULT_EXPIRATION_TIMEOUT, SUBNET, GolemNode
from golem_core.core.market_api import Demand, DemandBuilder, Payload, Proposal
from golem_core.core.market_api.resources.demand.demand_offer_base import defaults as dobm_defaults
from golem_core.core.payment_api import Allocation
from golem_core.managers.base import NegotiationManager

logger = logging.getLogger(__name__)


class AlfaNegotiationManager(NegotiationManager):
    def __init__(
        self, golem: GolemNode, get_allocation: Callable[[], Awaitable[Allocation]]
    ) -> None:
        self._golem = golem
        self._get_allocation = get_allocation
        self._negotiations: List[asyncio.Task] = []
        self._ready_offers: asyncio.Queue[Proposal] = asyncio.Queue()

    async def get_offer(self) -> Proposal:
        logger.debug("Returning offer")
        return await self._ready_offers.get()

    async def start_negotiation(self, payload: Payload) -> None:
        logger.debug("Starting negotiations")
        self._negotiations.append(asyncio.create_task(self._negotiate_task(payload)))

    async def stop_negotiation(self) -> None:
        for task in self._negotiations:
            logger.debug("Stopping negotiations")
            task.cancel()

    async def _negotiate_task(self, payload: Payload) -> None:
        allocation = await self._get_allocation()
        demand = await self._build_demand(allocation, payload)
        async for offer in self._negotiate(demand):
            await self._ready_offers.put(offer)

    async def _build_demand(self, allocation: Allocation, payload: Payload) -> Demand:
        logger.debug("Creating demand")
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
        return demand

    async def _negotiate(self, demand: Demand) -> AsyncIterator[Proposal]:
        try:
            async for initial in demand.initial_proposals():
                logger.debug("Got initial proposal")
                try:
                    pending = await initial.respond()
                except Exception as err:
                    logger.debug(
                        f"Unable to respond to initialproposal {initial.id}. Got {type(err)}\n{err}"
                    )
                    continue

                try:
                    # TODO IDK how to call `confirm` on a proposal in golem-core
                    confirmed = await pending.responses().__anext__()
                except StopAsyncIteration:
                    continue

                yield confirmed
        finally:
            self._golem.add_autoclose_resource(demand)
