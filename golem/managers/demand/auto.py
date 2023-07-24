import logging
from typing import Awaitable, Callable

from golem.managers.base import DemandManager
from golem.managers.mixins import BackgroundLoopMixin, WeightProposalScoringPluginsMixin
from golem.node import GolemNode
from golem.payload import Payload
from golem.resources import Allocation, Proposal
from golem.resources.demand.demand_builder import DemandBuilder
from golem.utils.logging import trace_span

logger = logging.getLogger(__name__)


class AutoDemandManager(BackgroundLoopMixin, WeightProposalScoringPluginsMixin, DemandManager):
    def __init__(
        self,
        golem: GolemNode,
        get_allocation: Callable[[], Awaitable[Allocation]],
        payload: Payload,
        *args,
        **kwargs,
    ) -> None:
        self._golem = golem
        self._get_allocation = get_allocation
        self._payload = payload

        super().__init__(*args, **kwargs)

    @trace_span(show_results=True)
    async def get_initial_proposal(self) -> Proposal:
        return await self.get_scored_proposal()

    @trace_span()
    async def _background_loop(self) -> None:
        allocation = await self._get_allocation()
        demand_builder = await self._prepare_demand_builder(allocation)

        demand = await demand_builder.create_demand(self._golem)
        demand.start_collecting_events()

        logger.debug(f"`{demand}` posted on market with `{demand_builder}`")

        try:
            async for initial_proposal in demand.initial_proposals():
                await self.manage_scoring(initial_proposal)
        finally:
            await demand.unsubscribe()

    @trace_span()
    async def _prepare_demand_builder(self, allocation: Allocation) -> DemandBuilder:
        # FIXME: Code looks duplicated as GolemNode.create_demand does the same
        demand_builder = DemandBuilder()

        await demand_builder.add_default_parameters(
            self._demand_offer_parser, allocations=[allocation]
        )

        await demand_builder.add(self._payload)

        return demand_builder
