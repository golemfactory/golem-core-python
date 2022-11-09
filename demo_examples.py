import asyncio
import sys

from golem_api import commands, GolemNode, Payload
from golem_api.mid import (
    Buffer, Chain, Map,
    default_negotiate, default_create_agreement, default_create_activity, default_prepare_activity,
)
from golem_api.low import Invoice
from golem_api.events import NewResource


IMAGE_HASH = "9a3b5d67b0b27746283cb5f287c13eab1beaa12d92a9f536b747c7ae"
PAYLOAD = Payload.from_image_hash(IMAGE_HASH)

async def max_3(in_stream):
    cnt = 0
    async for x in in_stream:
        yield x
        cnt += 1
        if cnt == 3:
            return

async def example_1():
    async with GolemNode() as golem:
        allocation = await golem.create_allocation(1)
        print(await allocation.get_data())
        await allocation.release()

async def example_2():
    async with GolemNode() as golem:
        allocations = await golem.allocations()
        for allocation in allocations:
            print(await allocation.get_data())

async def example_3():
    async with GolemNode() as golem:
        allocation = await golem.create_allocation(1, autoclose=False)
    print(allocation.id)

async def example_4():
    allocation_id = sys.argv[1]
    async with GolemNode() as golem:
        allocation = golem.allocation(allocation_id)
        await allocation.release()

async def example_5():
    activity_id = sys.argv[1]
    async with GolemNode() as golem:
        activity = golem.activity(activity_id)
        batch = await activity.execute_commands(commands.Run("date"))
        await batch.wait(5)
        date = batch.events[0].stdout.strip()
        print(f"Current date on {activity} is {date}")

async def example_6():
    async with GolemNode() as golem:
        allocation = await golem.create_allocation(1)
        demand = await golem.create_demand(PAYLOAD, allocations=[allocation])
        proposal = await demand.initial_proposals().__anext__()
        our_response = await proposal.respond()
        their_response = await our_response.responses().__anext__()
        agreement = await their_response.create_agreement()
        await agreement.confirm()
        await agreement.wait_for_approval()
        activity = await agreement.create_activity()
        print(activity.id)

async def example_7():
    async def get_their_responses(initial_proposal_stream):
        async for proposal in initial_proposal_stream:
            try:
                our_response = await proposal.respond()
                yield await our_response.responses().__anext__()
            except Exception:
                continue

    async with GolemNode() as golem:
        allocation = await golem.create_allocation(1)
        demand = await golem.create_demand(PAYLOAD, allocations=[allocation])
        their_response = await get_their_responses(demand.initial_proposals()).__anext__()
        print(their_response)

async def example_8():
    async with GolemNode() as golem:
        allocation = await golem.create_allocation(1)
        demand = await golem.create_demand(PAYLOAD, allocations=[allocation])

        chain = Chain(
            demand.initial_proposals(),
            Map(default_negotiate),
            Map(default_create_agreement),
            Map(default_create_activity),
            Buffer(size=2),
        )
        activity_1 = await chain.__anext__()
        activity_2 = await chain.__anext__()
        print(activity_1, activity_2)

async def example_9():
    async def use_activity(activity):
        batch = await activity.execute_commands(commands.Run("date"))
        await batch.wait(5)
        return batch.events[0].stdout.strip()

    async with GolemNode() as golem:
        allocation = await golem.create_allocation(1)
        demand = await golem.create_demand(PAYLOAD, allocations=[allocation])

        async for result in Chain(
            demand.initial_proposals(),
            Map(default_negotiate),
            Map(default_create_agreement),
            Map(default_create_activity),
            Map(default_prepare_activity),
            Map(use_activity),
            Buffer(size=2),
            max_3,
        ):
            print(result)

async def example_10():
    async def log_event(event):
        print(event)

    async with GolemNode() as golem:
        golem.event_bus.listen(log_event)

        allocation = await golem.create_allocation(1)
        demand = await golem.create_demand(PAYLOAD, allocations=[allocation])
        await demand.initial_proposals().__anext__()

async def example_11():
    wait_for_invoice = asyncio.Future()

    async def on_new_invoice_event(event):
        wait_for_invoice.set_result(event.resource)

    async with GolemNode() as golem:
        golem.event_bus.resource_listen(
            on_new_invoice_event, event_classes=[NewResource], resource_classes=[Invoice]
        )

        allocation = await golem.create_allocation(1)
        demand = await golem.create_demand(PAYLOAD, allocations=[allocation])

        async for agreement in Chain(
            demand.initial_proposals(),
            Map(default_negotiate),
            Map(default_create_agreement),
            Buffer(),
        ):
            break

        await agreement.terminate()
        invoice = await wait_for_invoice
        await invoice.accept_full(allocation)
        print(f"Accepted {invoice}! Nice!")


if __name__ == '__main__':
    asyncio.run(example_11())
