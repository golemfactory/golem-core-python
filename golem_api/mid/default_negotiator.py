from typing import Optional

from golem_api.low.market import Proposal
from .map import Map


async def negotiate(proposal: Proposal) -> Optional[Proposal]:
    our_response = await proposal.respond()
    async for their_response in our_response.responses():
        return their_response
    return None


class DefaultNegotiator(Map[Proposal, Proposal]):
    def __init__(self) -> None:
        return super().__init__(negotiate, True)
