import logging
from typing import Sequence, Set

from golem.managers.base import NegotiationManagerPlugin, PricingCallable, RejectProposal
from golem.payload import Properties
from golem.resources import DemandData, ProposalData

logger = logging.getLogger(__name__)


class BlacklistProviderId(NegotiationManagerPlugin):
    def __init__(self, blacklist: Sequence[str]) -> None:
        self._blacklist = blacklist

    async def __call__(self, demand_data: DemandData, proposal_data: ProposalData) -> None:
        logger.debug("Calling blacklist plugin...")

        provider_id = proposal_data.issuer_id

        if provider_id in self._blacklist:
            logger.debug(
                f"Calling blacklist plugin done with provider `{provider_id}` is blacklisted"
            )
            raise RejectProposal(f"Provider ID `{provider_id}` is blacklisted by the requestor")

        logger.debug(
            f"Calling blacklist plugin done with provider `{provider_id}` is not blacklisted"
        )


class AddChosenPaymentPlatform(NegotiationManagerPlugin):
    async def __call__(self, demand_data: DemandData, proposal_data: ProposalData) -> None:
        logger.debug("Calling chosen payment platform plugin...")

        if demand_data.properties.get("golem.com.payment.chosen-platform"):
            logger.debug(
                "Calling chosen payment platform plugin done, ignoring as platform already set"
            )
            return

        demand_platforms = self._get_payment_platform_from_properties(demand_data.properties)
        proposal_platforms = self._get_payment_platform_from_properties(proposal_data.properties)
        common_platforms = list(demand_platforms.intersection(proposal_platforms))

        if not common_platforms:
            raise RejectProposal("No common payment platform!")

        chosen_platform = common_platforms[0]

        demand_data.properties["golem.com.payment.chosen-platform"] = chosen_platform

        logger.debug(f"Calling chosen payment platform plugin done with `{chosen_platform}`...")

    def _get_payment_platform_from_properties(self, properties: Properties) -> Set[str]:
        return {
            property.split(".")[4]
            for property in properties
            if property.startswith("golem.com.payment.platform.") and property is not None
        }


class RejectIfCostsExceeds(NegotiationManagerPlugin):
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
