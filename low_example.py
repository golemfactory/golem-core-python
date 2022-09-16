import asyncio

from yapapi.payload import vm

from golem_api import GolemNode
from golem_api.events import ResourceEvent

IMAGE_HASH = "9a3b5d67b0b27746283cb5f287c13eab1beaa12d92a9f536b747c7ae"


async def example_1(allocation_id: str, demand_id: str, proposal_id: str) -> None:
    """Show existing allocation/demand/proposal"""
    golem = GolemNode()

    allocation = golem.allocation(allocation_id)
    demand = golem.demand(demand_id)
    proposal = golem.proposal(proposal_id, demand_id)

    print(allocation)
    print(demand)
    print(proposal)

    async with golem:
        await allocation.get_data()
        await demand.get_data()
        await proposal.get_data()

    print(allocation.data)
    print(demand.data)
    print(proposal.data)

    #   All objects are singletons
    assert allocation is golem.allocation(allocation_id)
    assert demand is golem.demand(demand_id)
    assert proposal is golem.proposal(proposal_id, demand_id)


async def example_2() -> None:
    """Show all current allocations/demands"""
    golem = GolemNode()
    async with golem:
        for allocation in await golem.allocations():
            print(allocation)

        for demand in await golem.demands():
            print(demand)


async def example_3() -> None:
    """Create new allocation, demand, fetch a single proposal, cleanup"""
    golem = GolemNode()
    async with golem:
        allocation = await golem.create_allocation(1)
        print(allocation)

        payload = await vm.repo(image_hash=IMAGE_HASH)
        demand = await golem.create_demand(payload, allocations=[allocation])
        print(demand)

        async for proposal in demand.initial_proposals():
            print(proposal)
            break

        #   NOTE: these are redundant because both demand and allocation were
        #         created in autoclose=True mode
        await demand.unsubscribe()
        await allocation.release()


async def example_4() -> None:
    """Respond to a proposal. Receive a conuterproposal. Reject it."""
    golem = GolemNode()
    async with golem:
        allocation = await golem.create_allocation(1)
        payload = await vm.repo(image_hash=IMAGE_HASH)
        demand = await golem.create_demand(payload, allocations=[allocation])

        #   Respond to proposals until we get a counterproposal
        async for proposal in demand.initial_proposals():
            our_response = await proposal.respond()
            print(f"We responded to {proposal} with {our_response}")
            try:
                their_response = await our_response.responses().__anext__()
                print(f"... and they responded with {their_response}")
                break
            except StopAsyncIteration:
                print("... and they rejected it")
                await our_response.get_data(force=True)
                assert our_response.data.state == "Rejected"

        #   Reject their counterproposal
        await their_response.reject()
        await their_response.get_data(force=True)
        assert their_response.data.state == "Rejected"
        print(f"... and we rejected it")

        #   The proposal tree
        assert their_response.parent is our_response
        assert our_response.parent is proposal
        assert proposal.parent is demand


async def example_5() -> None:
    """EventBus usage example"""
    golem = GolemNode()
    got_events = []

    async def on_event(event: ResourceEvent) -> None:
        got_events.append(event)

    golem.event_bus.resource_listen(on_event)
    async with golem:
        allocation = await golem.create_allocation(1)

    assert len(got_events) == 2
    assert got_events[0].resource == allocation
    assert got_events[1].resource == allocation

    from golem_api import events
    assert isinstance(got_events[0], events.NewResource)
    assert isinstance(got_events[1], events.ResourceClosed)


async def example_6() -> None:
    """Get an activity. Execute a hello world on it, using the "lowest level" interface."""
    golem = GolemNode()
    async with golem:
        allocation = await golem.create_allocation(1)
        payload = await vm.repo(image_hash=IMAGE_HASH)
        demand = await golem.create_demand(payload, allocations=[allocation])

        async for proposal in demand.initial_proposals():
            try:
                our_response = await proposal.respond()
            except Exception as e:
                print(str(e))
                continue

            try:
                their_response = await our_response.responses().__anext__()
            except StopAsyncIteration:
                continue

            agreement = await their_response.create_agreement()
            await agreement.confirm()
            await agreement.wait_for_approval()
            print(agreement)

            try:
                activity = await agreement.create_activity()
                break
            except Exception as e:
                print(str(e))

        print(activity)
        batch = await activity.raw_exec([
            {"deploy": {}},
            {"start": {}},
            {"run": {
                "entry_point": "/bin/echo",
                "args": ["hello", "world"],
                "capture": {
                    "stdout": {
                        "stream": {},
                    },
                    "stderr": {
                        "stream": {},
                    },
                }
            }},
            {"run": {
                "entry_point": "/bin/sleep",
                "args": ["5"],
                "capture": {
                    "stdout": {
                        "stream": {},
                    },
                    "stderr": {
                        "stream": {},
                    },
                }
            }},
        ])

        await batch.finished
        for ix, event in enumerate(batch.events):
            print("STDOUT", ix, event.index)
            print(event.stdout)
            print()

        print("STOPPING")
    print("STOPPED")


async def example_7():
    """Print most recent invoice and debit note received by this node"""
    golem = GolemNode()
    async with golem:
        invoice = (await golem.invoices())[-1]
        print(invoice)
        print(await invoice.get_data())

        debit_note = (await golem.debit_notes())[-1]
        print(debit_note)
        print(await debit_note.get_data())


async def main() -> None:
    # NOTE: this example assumes correct allocation/demand/proposal IDs
    # print("\n---------- EXAMPLE 1 -------------\n")
    # allocation_id = "b7bf70f9-529b-4901-9bb9-70080e97dbed"
    # demand_id = "01e23b27c3f34d99a2156b15796a8315-0c2cc2fb3200f6bd389811a29fe94d03ddd44949df9360b68fcef9da3fa1009b"
    # proposal_id = "R-8da944668deeade9d59dfe451656419e68fb04cf88c78c02ad905a7b0276ded6"
    # await example_1(allocation_id, demand_id, proposal_id)

    # print("\n---------- EXAMPLE 2 -------------\n")
    # await example_2()

    # print("\n---------- EXAMPLE 3 -------------\n")
    # await example_3()

    # print("\n---------- EXAMPLE 4 -------------\n")
    # await example_4()

    # print("\n---------- EXAMPLE 5 -------------\n")
    # await example_5()

    # print("\n---------- EXAMPLE 6 -------------\n")
    # await example_6()

    print("\n---------- EXAMPLE 7 -------------\n")
    await example_7()


if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(main())
