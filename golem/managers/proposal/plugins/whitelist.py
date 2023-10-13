import logging
from typing import Set

from golem.managers import ProposalManagerPlugin
from golem.resources import Proposal
from golem.utils.logging import trace_span

logger = logging.getLogger(__name__)


class WhitelistProviderIdPlugin(ProposalManagerPlugin):
    def __init__(self, whitelist: Set[str]) -> None:
        self._whitelist = whitelist

    @trace_span(show_results=True)
    async def get_proposal(self) -> Proposal:
        while True:
            proposal: Proposal = await self._get_proposal()
            proposal_data = await proposal.get_data()
            provider_id = proposal_data.issuer_id

            if provider_id in self._whitelist:
                return proposal

            if not proposal.initial:
                await proposal.reject("provider_id is not on whitelist")

            logger.debug(
                f"Provider id `{provider_id}` from proposal `{proposal}` is not on whitelist,"
                f" picking different proposal..."
            )
