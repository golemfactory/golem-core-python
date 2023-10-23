import asyncio
import logging
from copy import deepcopy
from datetime import datetime
from typing import Optional, Sequence, cast

from ya_market import ApiException

from golem.managers import ProposalManagerPlugin, RejectProposal
from golem.managers.base import ProposalNegotiator
from golem.payload import PayloadSyntaxParser, Properties
from golem.resources import DemandData, Proposal, ProposalData
from golem.utils.logging import trace_span

logger = logging.getLogger(__name__)


class NegotiatingPlugin(ProposalManagerPlugin):
    def __init__(
        self,
        demand_offer_parser: Optional[PayloadSyntaxParser] = None,
        proposal_negotiators: Optional[Sequence[ProposalNegotiator]] = None,
        *args,
        **kwargs,
    ) -> None:
        if demand_offer_parser is None:
            from golem.payload.parsers.textx import TextXPayloadSyntaxParser

            demand_offer_parser = TextXPayloadSyntaxParser()
        self._demand_offer_parser = demand_offer_parser
        self._proposal_negotiators: Sequence[ProposalNegotiator] = (
            list(proposal_negotiators) if proposal_negotiators is not None else []
        )

        self._success_count = 0
        self._fail_count = 0

        super().__init__(*args, **kwargs)

    @trace_span(show_results=True)
    async def get_proposal(self) -> Proposal:
        while True:
            proposal = await self._get_proposal()

            demand_data = await self._get_demand_data_from_proposal(proposal)

            try:
                negotiated_proposal = await self._negotiate_proposal(demand_data, proposal)
                self._success_count += 1
                logger.info(
                    f"Negotiation based on proposal `{proposal}` succeeded"
                    f"\nsuccess count: {self._success_count}/{self._success_count+self._fail_count}"
                )
                return negotiated_proposal
            except Exception:
                self._fail_count += 1
                logger.debug(
                    f"Negotiation based on proposal `{proposal}` failed, retrying with new one..."
                    f"\nsuccess count: {self._success_count}/{self._success_count+self._fail_count}"
                )

    @trace_span(show_arguments=True, show_results=True)
    async def _negotiate_proposal(
        self, demand_data: DemandData, offer_proposal: Proposal
    ) -> Proposal:
        while True:
            demand_data_after_negotiators = deepcopy(demand_data)

            try:
                await self._run_negotiators(demand_data_after_negotiators, offer_proposal)
            except RejectProposal:
                if not offer_proposal.initial:
                    await self._reject_proposal(offer_proposal)

                raise

            if not offer_proposal.initial and demand_data_after_negotiators == demand_data:
                return offer_proposal

            demand_data = demand_data_after_negotiators

            demand_proposal = await self._send_demand_proposal(offer_proposal, demand_data)
            new_offer_proposal = await self._wait_for_proposal_response(demand_proposal)

            offer_proposal = new_offer_proposal

    @trace_span()
    async def _wait_for_proposal_response(self, demand_proposal: Proposal) -> Proposal:
        try:
            return await demand_proposal.responses().__anext__()
        except StopAsyncIteration as e:
            raise RuntimeError("Failed to receive proposal response!") from e

    @trace_span()
    async def _send_demand_proposal(
        self, offer_proposal: Proposal, demand_data: DemandData
    ) -> Proposal:
        try:
            return await offer_proposal.respond(
                demand_data.properties,
                demand_data.constraints,
            )
        except (ApiException, asyncio.TimeoutError) as e:
            raise RuntimeError(f"Failed to send proposal response! {e}") from e

    @trace_span()
    async def _reject_proposal(self, offer_proposal: Proposal) -> None:
        await offer_proposal.reject()

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

        for negotiator in self._proposal_negotiators:
            negotiator_result = negotiator(demand_data_after_negotiators, proposal_data)

            if asyncio.iscoroutine(negotiator_result):
                negotiator_result = await negotiator_result

            if isinstance(negotiator_result, RejectProposal):
                raise negotiator_result

            # Note: Explicit identity to False desired here, not "falsy" check
            if negotiator_result is False:
                raise RejectProposal()
