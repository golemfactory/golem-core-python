from golem_core.core.activity_api.resources import Activity
from golem_core.core.market_api.resources import Agreement, Proposal


async def default_negotiate(proposal: Proposal) -> Proposal:
    """Negotiate a new :any:`Proposal` based on a given :any:`Proposal`."""
    our_response = await proposal.respond()
    async for their_response in our_response.responses():
        return their_response
    raise Exception(f"Negotiations based on {proposal} failed")


async def default_create_agreement(proposal: Proposal) -> Agreement:
    """Create a both-sides approved :any:`Agreement` based on a given :any:`Proposal`."""
    agreement = await proposal.create_agreement()
    await agreement.confirm()

    approved = await agreement.wait_for_approval()
    if approved:
        return agreement
    raise Exception(f"Agreement {agreement} created from {proposal} was not approved")


async def default_create_activity(agreement: Agreement) -> Activity:
    """Create a new :any:`Activity` for a given :any:`Agreement`."""
    return await agreement.create_activity()
