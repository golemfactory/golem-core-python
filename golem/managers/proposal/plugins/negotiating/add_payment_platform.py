import logging
from typing import Set

from golem.managers.base import ProposalNegotiator, RejectProposal
from golem.payload import Properties
from golem.resources import DemandData, ProposalData

logger = logging.getLogger(__name__)


class AddChosenPaymentPlatform(ProposalNegotiator):
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
