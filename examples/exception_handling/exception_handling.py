import asyncio
from typing import Callable, Tuple

from golem.event_bus import Event
from golem.node import GolemNode
from golem.payload import RepositoryVmPayload
from golem.pipeline import Buffer, Chain, DefaultPaymentHandler, Limit, Map
from golem.resources import (
    BatchError,
    BatchTimeoutError,
    default_create_activity,
    default_create_agreement,
    default_negotiate,
)
from golem.resources.activity import Activity, commands
from golem.utils.logging import DefaultLogger

PAYLOAD = RepositoryVmPayload("9a3b5d67b0b27746283cb5f287c13eab1beaa12d92a9f536b747c7ae")


async def trigger_exception(activity: Activity) -> None:
    try:
        batch = await activity.execute_commands(
            commands.Deploy(),
            commands.Start(),
            commands.Run("/ooops/no_such_command"),
        )
        await batch.wait(timeout=20)
    except (BatchError, BatchTimeoutError):
        # Handle exceptions directly in handler func
        raise


async def on_exception(func: Callable, args: Tuple, e: Exception) -> None:
    activity = args[0]
    print(f"Activity {activity} failed because of:\n{e}")
    # Handle exception in `on_exception` func
    if isinstance(e, BatchError) or isinstance(e, BatchTimeoutError):
        print(f"Batch stdout: {[event.stdout for event in e.batch.events]}")
        print(f"Batch stderr: {[event.stderr for event in e.batch.events]}")
    await activity.parent.close_all()


async def main() -> None:
    golem = GolemNode()
    await golem.event_bus.on(Event, DefaultLogger().on_event)

    async with golem:
        allocation = await golem.create_allocation(1.0)
        payment_handler = DefaultPaymentHandler(golem, allocation)
        demand = await golem.create_demand(PAYLOAD, allocations=[allocation])

        chain = Chain(
            demand.initial_proposals(),
            Map(default_negotiate),
            Map(default_create_agreement),
            Map(default_create_activity),
            Limit(1),
            Map(trigger_exception, on_exception=on_exception),
            Buffer(1),
        )

        async for result in chain:
            print(f"Finished with {result}")

        print("TASK DONE")
        await payment_handler.terminate_agreements()
        await payment_handler.wait_for_invoices()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    task = loop.create_task(main())
    try:
        loop.run_until_complete(task)
    except KeyboardInterrupt:
        task.cancel()
        try:
            loop.run_until_complete(task)
        except asyncio.CancelledError:
            pass
