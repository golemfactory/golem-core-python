import logging
from typing import Sequence

from golem_core.core.market_api import DemandBuilder, Proposal
from golem_core.managers.base import NegotiationPlugin
from golem_core.managers.negotiation.sequential import RejectProposal

logger = logging.getLogger(__name__)


class BlacklistProviderId(NegotiationPlugin):
    def __init__(self, blacklist: Sequence[str]) -> None:
        self._blacklist = blacklist

    async def __call__(self, demand_builder: DemandBuilder, proposal: Proposal) -> DemandBuilder:
        logger.debug("Calling blacklist plugin...")

        provider_id = proposal.data.issuer_id

        if provider_id in self._blacklist:
            logger.debug(
                f"Calling blacklist plugin done with provider `{provider_id}` is blacklisted"
            )
            raise RejectProposal(f"Provider ID `{provider_id}` is blacklisted by the requestor")

        logger.debug(
            f"Calling blacklist plugin done with provider `{provider_id}` is not blacklisted"
        )

        return demand_builder
