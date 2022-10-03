import asyncio

from golem_api.events import NewResource
from golem_api.low import DebitNote
from golem_api import GolemNode, commands


async def attach(debit_note_event: NewResource) -> None:
    debit_note = debit_note_event.resource
    activity_id = (await debit_note.get_data()).activity_id
    activity = debit_note.node.activity(activity_id)
    batch = await activity.execute_commands(
        commands.Run(["/bin/echo", "-n", f"ATTACHED TO ACTIVITY {activity}"]),
    )
    await batch.wait()
    print(batch.events[0].stdout)


async def main() -> None:
    golem = GolemNode()
    golem.event_bus.resource_listen(attach, [NewResource], [DebitNote])

    async with golem:
        await asyncio.sleep(1000)


asyncio.run(main())
