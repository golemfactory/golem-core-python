import asyncio
import logging
from copy import deepcopy
from typing import Optional, Sequence

from ya_market import ApiException

from golem.managers import ProposalManagerPlugin, RejectProposal
from golem.managers.base import ProposalNegotiator
from golem.resources import DemandData, Proposal
from golem.utils.logging import trace_span

logger = logging.getLogger(__name__)


class NegotiatingPlugin(ProposalManagerPlugin):
    def __init__(
        self,
        proposal_negotiators: Optional[Sequence[ProposalNegotiator]] = None,
        *args,
        **kwargs,
    ) -> None:
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
            demand_data = await proposal.demand.get_demand_data()

            try:
                negotiated_proposal = await self._negotiate_proposal(demand_data, proposal)
                self._success_count += 1
                logger.info(
                    f"Negotiation based on proposal `{proposal}` succeeded"
                    "\nsuccess count: "
                    f"{self._success_count}/{self._success_count + self._fail_count}"
                )
                return negotiated_proposal
            except Exception:
                self._fail_count += 1
                logger.debug(
                    f"Negotiation based on proposal `{proposal}` failed, retrying with new one..."
                    "\nsuccess count: "
                    f"{self._success_count}/{self._success_count + self._fail_count}",
                    exc_info=True,
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

    @trace_span()
    async def _run_negotiators(
        self, demand_data_after_negotiators: DemandData, offer_proposal: Proposal
    ):
        proposal_data = await offer_proposal.get_proposal_data()

        for negotiator in self._proposal_negotiators:
            negotiator_result = negotiator(demand_data_after_negotiators, proposal_data)

            if asyncio.iscoroutine(negotiator_result):
                negotiator_result = await negotiator_result

            if isinstance(negotiator_result, RejectProposal):
                raise negotiator_result

            # Note: Explicit identity to False desired here, not "falsy" check
            if negotiator_result is False:
                raise RejectProposal()
