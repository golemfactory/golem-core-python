import logging

from golem.managers.base import PricingCallable, ProposalNegotiator, RejectProposal
from golem.resources import DemandData, ProposalData

logger = logging.getLogger(__name__)


class RejectIfCostsExceeds(ProposalNegotiator):
    def __init__(
        self, cost: float, pricing_callable: PricingCallable, reject_on_unpricable=True
    ) -> None:
        self._cost = cost
        self._pricing_callable = pricing_callable
        self.reject_on_unpricable = reject_on_unpricable

    async def __call__(self, demand_data: DemandData, proposal_data: ProposalData) -> None:
        cost = self._pricing_callable(proposal_data)

        if cost is None and self.reject_on_unpricable:
            raise RejectProposal("Can't estimate costs!")

        if cost is not None and self._cost <= cost:
            raise RejectProposal(f"Exceeds estimated costs of `{self._cost}`!")
