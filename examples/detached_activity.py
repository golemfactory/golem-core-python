import asyncio

from golem.node import GolemNode
from golem.payload import RepositoryVmPayload
from golem.pipeline import Chain, Map
from golem.resources import Activity, Agreement, Proposal, default_negotiate
from golem.resources.activity import commands

PAYLOAD = RepositoryVmPayload("9a3b5d67b0b27746283cb5f287c13eab1beaa12d92a9f536b747c7ae")


async def create_agreement(proposal: Proposal) -> Agreement:
    agreement = await proposal.create_agreement(autoclose=False)
    await agreement.confirm()
    assert await agreement.wait_for_approval(), "Agreement not approved"
    return agreement


async def create_activity(agreement: Agreement) -> Activity:
    return await agreement.create_activity(autoclose=False)


async def prepare_activity(activity: Activity) -> Activity:
    batch = await activity.execute_commands(commands.Deploy(), commands.Start())
    await batch.wait(10)
    return activity


async def main() -> None:
    golem = GolemNode(collect_payment_events=False)

    async with golem:
        allocation = await golem.create_allocation(1)
        demand = await golem.create_demand(PAYLOAD, allocations=[allocation])

        chain = Chain(
            demand.initial_proposals(),
            Map(default_negotiate),
            Map(create_agreement),
            Map(create_activity),
            Map(prepare_activity),
        )
        activity_awaitable = await chain.__anext__()
        activity = await activity_awaitable
        print(activity.id)


if __name__ == "__main__":
    asyncio.run(main())
