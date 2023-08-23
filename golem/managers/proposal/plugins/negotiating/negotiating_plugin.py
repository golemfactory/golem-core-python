import asyncio
from copy import deepcopy
from datetime import datetime
from typing import List, Optional, Sequence, cast

from ya_market import ApiException

from golem.managers import ProposalManagerPlugin, RejectProposal
from golem.managers.base import Negotiator
from golem.payload import PayloadSyntaxParser, Properties, TextXPayloadSyntaxParser
from golem.resources import DemandData, Proposal, ProposalData
from golem.utils.logging import trace_span


class NegotiatingPlugin(ProposalManagerPlugin):
    def __init__(
        self,
        demand_offer_parser: Optional[PayloadSyntaxParser] = None,
        negotiators: Optional[Sequence[Negotiator]] = None,
        *args,
        **kwargs,
    ) -> None:
        self._demand_offer_parser = demand_offer_parser or TextXPayloadSyntaxParser()
        self._negotiators: List[Negotiator] = list(negotiators) if negotiators is not None else []

        super().__init__(*args, **kwargs)

    @trace_span(show_results=True)
    async def get_proposal(self) -> Proposal:
        while True:
            proposal = await self._get_proposal()

            demand_data = await self._get_demand_data_from_proposal(proposal)

            offer_proposal = await self._negotiate_proposal(demand_data, proposal)

            if offer_proposal is not None:
                return offer_proposal

    @trace_span(show_arguments=True, show_results=True)
    async def _negotiate_proposal(
        self, demand_data: DemandData, offer_proposal: Proposal
    ) -> Optional[Proposal]:
        while True:
            demand_data_after_negotiators = deepcopy(demand_data)

            try:
                await self._run_negotiators(demand_data_after_negotiators, offer_proposal)
            except RejectProposal as e:
                if not offer_proposal.initial:
                    await offer_proposal.reject(str(e))

                return None

            if not offer_proposal.initial and demand_data_after_negotiators == demand_data:
                return offer_proposal

            demand_data = demand_data_after_negotiators

            demand_proposal = await self._send_demand_proposal(offer_proposal, demand_data)
            if demand_proposal is None:
                return None

            new_offer_proposal = await self._wait_for_proposal_response(demand_proposal)
            if new_offer_proposal is None:
                return None

            offer_proposal = new_offer_proposal

    @trace_span()
    async def _wait_for_proposal_response(self, demand_proposal: Proposal) -> Optional[Proposal]:
        try:
            return await demand_proposal.responses().__anext__()
        except StopAsyncIteration:
            return None

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

    @trace_span()
    async def _run_negotiators(
        self, demand_data_after_negotiators: DemandData, offer_proposal: Proposal
    ):
        proposal_data = await self._get_proposal_data_from_proposal(offer_proposal)

        for negotiator in self._negotiators:
            negotiator_result = negotiator(demand_data_after_negotiators, proposal_data)

            if asyncio.iscoroutine(negotiator_result):
                negotiator_result = await negotiator_result

            if isinstance(negotiator_result, RejectProposal):
                raise negotiator_result

            # Note: Explicit identity to False desired here, not "falsy" check
            if negotiator_result is False:
                raise RejectProposal()
