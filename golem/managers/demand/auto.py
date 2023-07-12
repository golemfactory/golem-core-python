import asyncio
import inspect
import logging
from datetime import datetime
from typing import Awaitable, Callable, List, Optional, Sequence, Tuple, cast

from golem.managers.base import (
    DemandManager,
    ManagerException,
    ManagerPluginsMixin,
    ManagerPluginWithOptionalWeight,
)
from golem.node import GolemNode
from golem.node.node import GolemNode
from golem.payload import Payload, Properties
from golem.payload.parsers.textx.parser import TextXPayloadSyntaxParser
from golem.resources import Allocation, Proposal, ProposalData
from golem.resources.demand.demand_builder import DemandBuilder
from golem.resources.proposal.proposal import Proposal
from golem.utils.asyncio import create_task_with_logging
from golem.utils.logging import trace_span

logger = logging.getLogger(__name__)


class AutoDemandManager(ManagerPluginsMixin[ManagerPluginWithOptionalWeight], DemandManager):
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

        self._demand_offer_parser = TextXPayloadSyntaxParser()

        self._scored_proposals: List[Tuple[float, Proposal]] = []
        self._scored_proposals_condition = asyncio.Condition()

        self._manager_loop_task: Optional[asyncio.Task] = None

        super().__init__(*args, **kwargs)

    @trace_span()
    async def start(self) -> None:
        if self.is_started():
            raise ManagerException("Already started!")

        self._manager_loop_task = create_task_with_logging(self._manager_loop())

    @trace_span()
    async def stop(self) -> None:
        if not self.is_started():
            raise ManagerException("Already stopped!")

        self._manager_loop_task.cancel()
        self._manager_loop_task = None

    def is_started(self) -> bool:
        return self._manager_loop_task is not None and not self._manager_loop_task.done()

    async def get_initial_proposal(self) -> Proposal:
        async with self._scored_proposals_condition:
            await self._scored_proposals_condition.wait_for(lambda: 0 < len(self._scored_proposals))

            score, proposal = self._scored_proposals.pop(0)

        return proposal

    @trace_span()
    async def _manager_loop(self) -> None:
        allocation = await self._get_allocation()
        demand_builder = await self._prepare_demand_builder(allocation)

        demand = await demand_builder.create_demand(self._golem)
        demand.start_collecting_events()

        try:
            async for initial_proposal in demand.initial_proposals():
                await self._manage_scoring(initial_proposal)
        finally:
            await demand.unsubscribe()

    async def _prepare_demand_builder(self, allocation: Allocation) -> DemandBuilder:
        # FIXME: Code looks duplicated as GolemNode.create_demand does the same
        demand_builder = DemandBuilder()

        await demand_builder.add_default_parameters(
            self._demand_offer_parser, allocations=[allocation]
        )

        await demand_builder.add(self._payload)

        return demand_builder

    @trace_span()
    async def _manage_scoring(self, proposal: Proposal) -> None:
        async with self._scored_proposals_condition:
            all_proposals = list(sp[1] for sp in self._scored_proposals)
            all_proposals.append(proposal)

            self._scored_proposals = await self._do_scoring(all_proposals)

            self._scored_proposals_condition.notify_all()

    async def _do_scoring(self, proposals: Sequence[Proposal]):
        proposals_data = await self._get_proposals_data_from_proposals(proposals)
        proposal_scores = await self._run_plugins(proposals_data)

        scored_proposals = self._calculate_proposal_score(proposals, proposal_scores)
        scored_proposals.sort(key=lambda x: x[0], reverse=True)

        return scored_proposals

    @trace_span()
    async def _run_plugins(
        self, proposals_data: Sequence[ProposalData]
    ) -> Sequence[Tuple[float, Sequence[float]]]:
        proposal_scores = []

        for plugin in self._plugins:
            if isinstance(plugin, (list, tuple)):
                weight, plugin = plugin
            else:
                weight = 1

            plugin_scores = plugin(proposals_data)

            if inspect.isawaitable(plugin_scores):
                plugin_scores = await plugin_scores

            proposal_scores.append((weight, plugin_scores))

        return proposal_scores

    def _calculate_proposal_score(
        self,
        proposals: Sequence[Proposal],
        plugin_scores: Sequence[Tuple[float, Sequence[float]]],
    ) -> List[Tuple[float, Proposal]]:
        # FIXME: can this be refactored?
        return [
            (
                self._calculate_weighted_score(
                    self._transpose_plugin_scores(proposal_index, plugin_scores)
                ),
                proposal,
            )
            for proposal_index, proposal in enumerate(proposals)
        ]

    def _calculate_weighted_score(
        self, proposal_weighted_scores: Sequence[Tuple[float, float]]
    ) -> float:
        if not proposal_weighted_scores:
            return 0

        weighted_sum = sum(pws[0] * pws[1] for pws in proposal_weighted_scores)
        weights_sum = sum(pws[0] for pws in proposal_weighted_scores)

        return weighted_sum / weights_sum

    def _transpose_plugin_scores(
        self, proposal_index: int, plugin_scores: Sequence[Tuple[float, Sequence[float]]]
    ) -> Sequence[Tuple[float, float]]:
        # FIXME: can this be refactored?
        return [
            (plugin_weight, plugin_scores[proposal_index])
            for plugin_weight, plugin_scores in plugin_scores
            if plugin_scores[proposal_index] is None
        ]

    async def _get_proposals_data_from_proposals(
        self, proposals: Sequence[Proposal]
    ) -> Sequence[ProposalData]:
        result = []

        for proposal in proposals:
            data = await proposal.get_data()

            constraints = self._demand_offer_parser.parse_constraints(data.constraints)

            result.append(
                ProposalData(
                    properties=Properties(data.properties),
                    constraints=constraints,
                    proposal_id=data.proposal_id,
                    issuer_id=data.issuer_id,
                    state=data.state,
                    timestamp=cast(datetime, data.timestamp),
                    prev_proposal_id=data.prev_proposal_id,
                )
            )

        return result
