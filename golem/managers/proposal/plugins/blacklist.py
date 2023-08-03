from typing import Sequence

from golem.managers import ProposalManagerPlugin
from golem.resources import Proposal
from golem.utils.logging import trace_span


class BlacklistProviderId(ProposalManagerPlugin):
    def __init__(self, blacklist: Sequence[str]) -> None:
        self._blacklist = blacklist

    @trace_span(show_results=True)
    async def get_proposal(self) -> Proposal:
        while True:
            proposal: Proposal = await self._get_proposal_callback()
            proposal_data = await proposal.get_data()
            provider_id = proposal_data.issuer_id
            if provider_id not in self._blacklist:
                break
            if not proposal.initial:
                await proposal.reject("provider_id on blacklist")
        return proposal
