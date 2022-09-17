from typing import Optional

from golem_api.low.market import Proposal
from .buffered_pipe import BufferedPipe


class DefaultNegotiator(BufferedPipe[Proposal, Proposal]):
    """IN: any :any:`Proposal`. OUT: a :any:`Proposal` that can be used as a base for an :any:`Agreement`"""

    async def _process_single_item(self, proposal: Proposal) -> Optional[Proposal]:
        our_response = await proposal.respond()
        async for their_response in our_response.responses():
            return their_response
        return None
