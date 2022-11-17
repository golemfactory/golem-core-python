import asyncio
from contextlib import asynccontextmanager
from tempfile import TemporaryDirectory
from os import path
from typing import AsyncGenerator, Optional

from golem_api import GolemNode, commands, Script, Payload
from golem_api.events import ResourceEvent
from golem_api.low import Activity
from golem_api.low.exceptions import BatchError, CommandFailed, CommandCancelled

PAYLOAD = Payload.from_image_hash("9a3b5d67b0b27746283cb5f287c13eab1beaa12d92a9f536b747c7ae")


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

        demand = await golem.create_demand(PAYLOAD, allocations=[allocation])
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
        demand = await golem.create_demand(PAYLOAD, allocations=[allocation])

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
    """Print most recent invoice and debit note received by this node"""
    golem = GolemNode()
    async with golem:
        invoice = (await golem.invoices())[-1]
        print(invoice)
        print(await invoice.get_data())

        debit_note = (await golem.debit_notes())[-1]
        print(debit_note)
        print(await debit_note.get_data())


@asynccontextmanager
async def get_activity(golem: Optional[GolemNode] = None) -> AsyncGenerator[Activity, None]:
    """Create a single activity"""
    if golem is None:
        golem = GolemNode()

    async with golem:
        allocation = await golem.create_allocation(1)
        demand = await golem.create_demand(PAYLOAD, allocations=[allocation])

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
        yield activity


async def example_7() -> None:
    """Use the direct interface of the activity"""
    async with get_activity() as activity:
        assert activity.idle
        batch = await activity.execute_commands(
            commands.Deploy(),
            commands.Start(),
            commands.Run(["/bin/echo", "-n", "hello", "world"]),
            commands.Run(["/bin/sleep", "2"]),
        )
        assert not activity.idle
        await batch.wait(timeout=10)
        assert batch.done

        assert activity.idle
        for event in batch.events:
            print(event)
            # print(f"Event {event.index} stdout: {event.stdout}")


async def example_8() -> None:
    """Send a batch using the Script interface"""
    async with get_activity() as activity:
        script = Script()
        script.add_command(commands.Deploy())
        script.add_command(commands.Start())
        x = script.add_command(commands.Run(["/bin/echo", "-n", "hello world from script"]))
        script.add_command(commands.Run(["/bin/sleep", "5"]))
        y = script.add_command(commands.Run(["/bin/echo", "-n", "another result"]))
        script.add_command(commands.Run(["/bin/sleep", "5"]))

        batch = await activity.execute_script(script)

        print(await x)
        print(await y)
        await batch.wait(10)
        print("Batch finished")


async def example_9() -> None:
    """Send an invalid batch using the Script interface"""
    async with get_activity() as activity:
        script = Script()
        script.add_command(commands.Deploy())
        script.add_command(commands.Start())

        success_result = script.add_command(commands.Run(["/bin/echo", "-n", "This works"]))
        failed_result = script.add_command(commands.Run(["/bin/ooops/this_looks_broken"]))
        never_result = script.add_command(commands.Run(["/bin/echo", "We won't get here"]))

        batch = await activity.execute_script(script)

        success = await success_result
        print(f"Command succesful: {success.stdout}")

        try:
            await failed_result
        except CommandFailed as e:
            print(f"Command failed: {e}")

        try:
            await never_result
        except CommandCancelled as e:
            print(f"Previous command failed: {e}")

        last_event = batch.events[-1]
        assert last_event.result == 'Error'


async def example_10() -> None:
    """Send a file"""
    async with get_activity() as activity:
        with TemporaryDirectory() as tmpdir:
            local_fname = path.join(tmpdir, "in_file.txt")
            in_file_text = "Hello world inside a file"

            with open(local_fname, 'w') as f:
                f.write(in_file_text)

            remote_fname = "/golem/resource/in_file.txt"
            batch = await activity.execute_commands(
                commands.Deploy(),
                commands.Start(),
                commands.SendFile(local_fname, remote_fname),
                commands.Run(f"cat {remote_fname}"),
            )
            await batch.wait(5)
            assert batch.events[-1].stdout == in_file_text


async def example_11() -> None:
    """Download a file"""
    async with get_activity() as activity:
        with TemporaryDirectory() as tmpdir:
            local_fname = path.join(tmpdir, "out_file.txt")
            remote_fname = "/golem/output/out_file.txt"
            out_file_text = "Provider wrote this"
            batch = await activity.execute_commands(
                commands.Deploy(),
                commands.Start(),
                commands.Run(f"echo -n '{out_file_text}' > {remote_fname}"),
                commands.DownloadFile(remote_fname, local_fname),
            )
            await batch.wait(5)
            with open(local_fname, 'r') as f:
                assert f.read() == out_file_text


async def example_12() -> None:
    """Batch.wait() with/without ignore_errors"""
    async with get_activity() as activity:
        batch = await activity.execute_commands(
            commands.Deploy(),
            commands.Start(),
            commands.Run("/invalid/command")
        )

        #   Wait, raise errors
        try:
            await batch.wait(5)
            assert False, "Batch didn't fail"
        except BatchError as e:
            print(f"Got expected exception: {e}")

        #   Wait, ignore errors (it doesn't matter if the batch already finished)
        await batch.wait(ignore_errors=True)


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

    # print("\n---------- EXAMPLE 7 -------------\n")
    # await example_7()

    # print("\n---------- EXAMPLE 8 -------------\n")
    # await example_8()

    # print("\n---------- EXAMPLE 9 -------------\n")
    # await example_9()

    # print("\n---------- EXAMPLE 10 -------------\n")
    # await example_10()

    # print("\n---------- EXAMPLE 11 -------------\n")
    # await example_11()

    print("\n---------- EXAMPLE 12 -------------\n")
    await example_12()


if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(main())
