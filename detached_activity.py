import asyncio
from golem_api import GolemNode, Payload, commands
from golem_api.mid import Chain, Map, default_negotiate
from golem_api.low import Activity, Agreement, Proposal

PAYLOAD = Payload.from_image_hash("9a3b5d67b0b27746283cb5f287c13eab1beaa12d92a9f536b747c7ae")


async def create_agreement(proposal: Proposal) -> Agreement:
    agreement = await proposal.create_agreement(autoclose=False)
    await agreement.confirm()
    assert await agreement.wait_for_approval(), "Agreement not approved"
    return agreement


async def create_activity(agreement: Agreement) -> Activity:
    return await agreement.create_activity(autoclose=False)


async def main():
    golem = GolemNode(collect_payment_events=False)

    async with golem:
        allocation = await golem.create_allocation(1)
        demand = await golem.create_demand(PAYLOAD, allocations=[allocation])

        chain = Chain(
            demand.initial_proposals(),
            Map(default_negotiate),
            Map(create_agreement),
            Map(create_activity),
        )
        activity_awaitable = await chain.__anext__()
        activity = await activity_awaitable
        batch = await activity.execute_commands(commands.Deploy(), commands.Start())
        await batch.wait(10)
        print(activity.id)


if __name__ == '__main__':
    asyncio.run(main())
