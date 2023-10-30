import logging
from datetime import datetime
from typing import cast

from golem.managers.base import PricingCallable, ProposalManagerPlugin
from golem.payload import Constraints, Properties
from golem.resources import Proposal, ProposalData
from golem.utils.logging import trace_span

logger = logging.getLogger(__name__)


class RejectIfCostsExceeds(ProposalManagerPlugin):
    def __init__(
        self, cost: float, pricing_callable: PricingCallable, reject_on_unpriceable=True
    ) -> None:
        self._cost = cost
        self._pricing_callable = pricing_callable
        self._reject_on_unpriceable = reject_on_unpriceable

    @trace_span(show_results=True)
    async def get_proposal(self) -> Proposal:
        while True:
            proposal: Proposal = await self._get_proposal()
            proposal_data = await self._get_proposal_data_from_proposal(proposal)

            cost = self._pricing_callable(proposal_data)

            if cost is None and self._reject_on_unpriceable:
                if not proposal.initial:
                    await proposal.reject("Can't estimate costs!")

                logger.debug(
                    "Can't estimate proposal `%s` costs `%s`, picking different one...",
                    proposal,
                    self._pricing_callable,
                )

                continue

            if cost is not None and self._cost <= cost:
                if not proposal.initial:
                    await proposal.reject(
                        f"Exceeds costs `{self._pricing_callable}` limit of `{self._cost}`!"
                    )

                logger.debug(
                    "Proposal `%s` costs `%s` of `%f` exceeds limit of `%f`,"
                    " picking different one...",
                    proposal,
                    self._pricing_callable,
                    cost,
                    self._cost,
                )

                continue

            return proposal

    async def _get_proposal_data_from_proposal(self, proposal: Proposal) -> ProposalData:
        data = await proposal.get_data()

        return ProposalData(
            properties=Properties(data.properties),
            constraints=Constraints(),
            proposal_id=data.proposal_id,
            issuer_id=data.issuer_id,
            state=data.state,
            timestamp=cast(datetime, data.timestamp),
            prev_proposal_id=data.prev_proposal_id,
        )
