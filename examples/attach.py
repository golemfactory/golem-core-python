import asyncio
import sys

from golem.node import GolemNode
from golem.resources import DebitNote, NewResource
from golem.resources.activity import commands
from golem.resources.debit_note.events import NewDebitNote

ACTIVITY_ID = sys.argv[1].strip()


async def accept_debit_note(payment_event: NewResource) -> None:
    debit_note: DebitNote = payment_event.resource

    this_activity_id = (await debit_note.get_data()).activity_id
    if this_activity_id == ACTIVITY_ID:
        allocation = await debit_note.node.create_allocation(1)
        await debit_note.accept_full(allocation)
        print(f"Accepted debit note {debit_note} using single-use {allocation}")
        await allocation.release()


async def main() -> None:
    golem = GolemNode()
    await golem.event_bus.on(NewDebitNote, accept_debit_note)

    async with golem:
        activity = golem.activity(ACTIVITY_ID)
        while True:
            batch = await activity.execute_commands(commands.Run("date"))
            await batch.wait(5)
            assert batch.events[-1].stdout is not None
            print(f"Current date on {activity} is {batch.events[-1].stdout.strip()}")
            await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
