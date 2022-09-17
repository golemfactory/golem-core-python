from typing import Optional

from golem_api.low.market import Agreement, Proposal
from .buffered_pipe import BufferedPipe


class AgreementCreator(BufferedPipe[Proposal, Agreement]):
    """Uses a :any:`Proposal` to create an :any:`Agreement`, confirms it and waits for approval."""

    async def _process_single_item(self, proposal: Proposal) -> Optional[Agreement]:
        agreement = await proposal.create_agreement()
        await agreement.confirm()

        approved = await agreement.wait_for_approval()
        if approved:
            return agreement
        return None
