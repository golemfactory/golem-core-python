from golem_api.low.market import Agreement, Proposal
from .map import Map


async def create_agreement(proposal: Proposal) -> Agreement:
    agreement = await proposal.create_agreement()
    await agreement.confirm()

    approved = await agreement.wait_for_approval()
    if approved:
        return agreement
    raise Exception("Agreement {agreement} created from {proposal} was not approved")


class AgreementCreator(Map[Proposal, Agreement]):
    def __init__(self) -> None:
        return super().__init__(create_agreement, True)
