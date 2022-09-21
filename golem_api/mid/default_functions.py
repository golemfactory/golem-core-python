from golem_api.low import Activity, Agreement, Proposal


async def default_negotiate(proposal: Proposal) -> Proposal:
    our_response = await proposal.respond()
    async for their_response in our_response.responses():
        return their_response
    raise Exception(f"Negotiations based on {proposal} failed")


async def default_create_agreement(proposal: Proposal) -> Agreement:
    agreement = await proposal.create_agreement()
    await agreement.confirm()

    approved = await agreement.wait_for_approval()
    if approved:
        return agreement
    raise Exception("Agreement {agreement} created from {proposal} was not approved")


async def default_create_activity(agreement: Agreement) -> Activity:
    return await agreement.create_activity()
