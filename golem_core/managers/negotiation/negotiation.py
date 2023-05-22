import asyncio
from datetime import datetime, timezone
from typing import Any, Awaitable, Dict, List

from golem_core.core.events import EventBus
from golem_core.core.golem_node.golem_node import DEFAULT_EXPIRATION_TIMEOUT, SUBNET, GolemNode
from golem_core.core.market_api import Demand, DemandBuilder, Payload, Proposal
from golem_core.core.market_api.resources.demand.demand_offer_base import defaults as dobm_defaults
from golem_core.core.payment_api import Allocation
from golem_core.core.resources import ResourceEvent
from golem_core.managers.base import NegotiationManager


class AlfaNegotiationManager(NegotiationManager):
    def __init__(self, golem: GolemNode, get_allocation: Awaitable) -> None:
        self._golem = golem
        self._event_bus: EventBus = self._golem.event_bus
        self._get_allocation = get_allocation
        self._negotiations: List[asyncio.Task] = []
        self._offer_generators: Dict[Payload, Any] = {}  # TODO typing gneerator

    async def get_offer(self, payload) -> Proposal:
        offer_generator = await self._get_offer_generator(payload)
        return await anext(offer_generator)

    async def _get_offer_generator(self, payload) -> Any:
        if self._offer_generators.get(payload) is None:
            allocation = await self._get_allocation()
            demand = await self._build_demand(allocation, payload)
            self._offer_generators[payload] = self._negotiate(demand)
        return self._offer_generators[payload]

    async def _negotiate(self, demand: Demand) -> None:
        try:
            async for initial in demand.initial_proposals():
                try:
                    pending = await initial.respond()
                except Exception as err:
                    print(
                        f"Unable to respond to initial proposal {initial.id}. Got {type(err)}\n{err}"
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

    async def _build_demand(self, allocation: Allocation, payload: Payload) -> Demand:
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

    async def start_negotiation(self, payload: Payload) -> None:
        self._negotiations.append(asyncio.create_task(self._negotiate_task(payload)))

    async def stop_negotiation(self) -> None:
        for task in self._negotiations:
            task.cancel()

    async def _negotiate_task(self, payload: Payload) -> None:
        offer_generator = await self._get_offer_generator(payload)
        async for offer in offer_generator:
            self._event_bus.emit(ResourceEvent(offer))
