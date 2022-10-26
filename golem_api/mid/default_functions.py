from golem_api.commands import Deploy, Start
from golem_api.low import Activity, Agreement, Proposal


async def default_negotiate(proposal: Proposal) -> Proposal:
    """Negotiates a new :any:`Proposal` (that can be later turned into an :any:`Agreement`)
    based on a given :any:`Proposal`."""
    our_response = await proposal.respond()
    async for their_response in our_response.responses():
        return their_response
    raise Exception(f"Negotiations based on {proposal} failed")


async def default_create_agreement(proposal: Proposal) -> Agreement:
    """Creates a ready-to-use (i.e. approved by both sides) :any:`Agreement` based on a given :any:`Proposal`."""
    agreement = await proposal.create_agreement()
    await agreement.confirm()

    approved = await agreement.wait_for_approval()
    if approved:
        return agreement
    raise Exception(f"Agreement {agreement} created from {proposal} was not approved")


async def default_create_activity(agreement: Agreement) -> Activity:
    """Creates a new :any:`Activity` for a given :any:`Agreement`."""
    return await agreement.create_activity()


async def default_prepare_activity(activity: Activity) -> Activity:
    """Executes Deploy() and Start() commands on a given :any:`Activity`. Returns the same :any:`Activity`.

    If the commands fail, destroys the :any:`Activity` and terminates the corresponding :any:`Agreement`.
    """
    try:
        batch = await activity.execute_commands(Deploy(), Start())
        await batch.wait(timeout=300)
        assert batch.success, batch.events[-1].message
    except Exception:
        await activity.parent.close_all()
        raise
    return activity
