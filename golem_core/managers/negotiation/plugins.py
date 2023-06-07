import logging
from typing import Sequence

from golem_core.core.market_api.resources.proposal import ProposalData
from golem_core.managers.base import NegotiationPlugin
from golem_core.managers.negotiation.sequential import RejectProposal

logger = logging.getLogger(__name__)


class BlacklistProviderId(NegotiationPlugin):
    def __init__(self, blacklist: Sequence[str]) -> None:
        self._blacklist = blacklist

    async def __call__(
        self, demand_proposal_data: ProposalData, offer_proposal_data: ProposalData
    ) -> None:
        logger.debug("Calling blacklist plugin...")

        provider_id = offer_proposal_data.issuer_id

        if provider_id in self._blacklist:
            logger.debug(
                f"Calling blacklist plugin done with provider `{provider_id}` is blacklisted"
            )
            raise RejectProposal(f"Provider ID `{provider_id}` is blacklisted by the requestor")

        logger.debug(
            f"Calling blacklist plugin done with provider `{provider_id}` is not blacklisted"
        )


class MidAgreementPayment(NegotiationPlugin):
    pass
