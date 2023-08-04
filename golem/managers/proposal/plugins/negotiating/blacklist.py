import logging
from typing import Sequence

from golem.managers.base import Negotiator, RejectProposal
from golem.resources import DemandData, ProposalData

logger = logging.getLogger(__name__)


class BlacklistProviderIdNegotiator(Negotiator):
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
