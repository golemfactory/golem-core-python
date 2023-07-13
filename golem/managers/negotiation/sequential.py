import asyncio
import logging
from copy import deepcopy
from datetime import datetime
from typing import Awaitable, Callable, Optional, cast

from ya_market import ApiException

from golem.managers.base import (
    ContextManagerLoopMixin,
    ManagerPluginsMixin,
    NegotiationManager,
    NegotiationManagerPlugin,
    RejectProposal,
)
from golem.node import GolemNode
from golem.payload import Properties
from golem.payload.parsers.textx import TextXPayloadSyntaxParser
from golem.resources import DemandData, Proposal, ProposalData
from golem.utils.logging import trace_span

logger = logging.getLogger(__name__)


class SequentialNegotiationManager(
    ContextManagerLoopMixin, ManagerPluginsMixin[NegotiationManagerPlugin], NegotiationManager
):
    # TODO remove unused methods
    def __init__(
        self,
        golem: GolemNode,
        get_initial_proposal: Callable[[], Awaitable[Proposal]],
        *args,
        **kwargs,
    ) -> None:
        self._golem = golem
        self._get_initial_proposal = get_initial_proposal

        self._eligible_proposals: asyncio.Queue[Proposal] = asyncio.Queue()
        self._demand_offer_parser = TextXPayloadSyntaxParser()

        super().__init__(*args, **kwargs)

    @trace_span()
    async def get_draft_proposal(self) -> Proposal:
        return await self._eligible_proposals.get()

    @trace_span()
    async def _manager_loop(self) -> None:
        while True:  # TODO add buffer
            proposal = await self._get_initial_proposal()

            demand_data = await self._get_demand_data_from_proposal(proposal)

            offer_proposal = await self._negotiate_proposal(demand_data, proposal)

            if offer_proposal is not None:
                await self._eligible_proposals.put(offer_proposal)

    @trace_span()
    async def _negotiate_proposal(
        self, demand_data: DemandData, offer_proposal: Proposal
    ) -> Optional[Proposal]:
        while True:
            demand_data_after_plugins = deepcopy(demand_data)

            try:
                await self._run_plugins(demand_data_after_plugins, offer_proposal)
            except RejectProposal as e:
                logger.debug(f"Proposal `{offer_proposal}` was rejected by plugins")

                if not offer_proposal.initial:
                    await offer_proposal.reject(str(e))

                return None

            if not offer_proposal.initial and demand_data_after_plugins == demand_data:
                return offer_proposal

            demand_data = demand_data_after_plugins

            demand_proposal = await self._send_demand_proposal(offer_proposal, demand_data)
            if demand_proposal is None:
                return None

            new_offer_proposal = await self._wait_for_proposal_response(demand_proposal)
            if new_offer_proposal is None:
                return None

            logger.debug(
                f"Proposal `{offer_proposal}` received counter proposal `{new_offer_proposal}`"
            )

            offer_proposal = new_offer_proposal

    @trace_span()
    async def _run_plugins(self, demand_data_after_plugins: DemandData, offer_proposal: Proposal):
        proposal_data = await self._get_proposal_data_from_proposal(offer_proposal)

        for plugin in self._plugins:
            plugin_result = plugin(demand_data_after_plugins, proposal_data)

            if asyncio.iscoroutine(plugin_result):
                plugin_result = await plugin_result

            if isinstance(plugin_result, RejectProposal):
                raise plugin_result

            # Note: Explicit identity to False desired here, not "falsy" check
            if plugin_result is False:
                raise RejectProposal()

    @trace_span()
    async def _send_demand_proposal(
        self, offer_proposal: Proposal, demand_data: DemandData
    ) -> Optional[Proposal]:
        try:
            return await offer_proposal.respond(
                demand_data.properties,
                demand_data.constraints,
            )
        except (ApiException, asyncio.TimeoutError):
            return None

    @trace_span()
    async def _wait_for_proposal_response(self, demand_proposal: Proposal) -> Optional[Proposal]:
        try:
            return await demand_proposal.responses().__anext__()
        except StopAsyncIteration:
            return None

    async def _get_demand_data_from_proposal(self, proposal: Proposal) -> DemandData:
        # FIXME: Unnecessary serialisation from DemandBuilder to Demand,
        #  and from Demand to ProposalData
        data = await proposal.demand.get_data()

        # TODO: Make constraints parsing lazy
        constraints = self._demand_offer_parser.parse_constraints(data.constraints)

        return DemandData(
            properties=Properties(data.properties),
            constraints=constraints,
            demand_id=data.demand_id,
            requestor_id=data.requestor_id,
            timestamp=cast(datetime, data.timestamp),
        )

    async def _get_proposal_data_from_proposal(self, proposal: Proposal) -> ProposalData:
        data = await proposal.get_data()

        constraints = self._demand_offer_parser.parse_constraints(data.constraints)

        return ProposalData(
            properties=Properties(data.properties),
            constraints=constraints,
            proposal_id=data.proposal_id,
            issuer_id=data.issuer_id,
            state=data.state,
            timestamp=cast(datetime, data.timestamp),
            prev_proposal_id=data.prev_proposal_id,
        )
