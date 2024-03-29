import asyncio
from datetime import timedelta
from random import random
from typing import AsyncIterator, Callable, Tuple

from examples.task_api_draft.task_api.activity_pool import ActivityPool
from golem.events_bus import Event
from golem.node import GolemNode
from golem.payload import RepositoryVmPayload
from golem.pipeline import Buffer, Chain, DefaultPaymentHandler, Map, Sort, Zip
from golem.resources import (
    Proposal,
    default_create_activity,
    default_create_agreement,
    default_negotiate,
)
from golem.resources.activity import Activity, commands
from golem.utils.logging import DefaultLogger

PAYLOAD = RepositoryVmPayload("9a3b5d67b0b27746283cb5f287c13eab1beaa12d92a9f536b747c7ae")


async def score_proposal(proposal: Proposal) -> float:
    return random()


async def prepare_activity(activity: Activity) -> Activity:
    batch = await activity.execute_commands(
        commands.Deploy(),
        commands.Start(),
        commands.Run(["/bin/echo", "-n", f"ACTIVITY {activity.id} IS READY"]),
    )
    await batch.wait(timeout=10)
    assert (
        batch.events[-1].stdout is not None and "IS READY" in batch.events[-1].stdout
    ), "Prepare activity failed"
    print(batch.events[-1].stdout)
    return activity


async def execute_task(activity: Activity, task_data: int) -> str:
    assert activity.idle, f"Got a non-idle activity {activity}"
    command = commands.Run(["/bin/echo", "-n", f"Executed task {task_data} on {activity}"])
    batch = await activity.execute_commands(command)
    await batch.wait(timeout=3)

    result = batch.events[-1].stdout
    assert (
        result is not None and "Executed task" in result
    ), f"Got an incorrect result for {task_data}: {result}"

    if random() > 0.9:
        1 / 0

    return result


task_cnt = 20
task_data = list(range(task_cnt))


async def on_exception(func: Callable, args: Tuple, e: Exception) -> None:
    activity, in_data = args
    task_data.append(in_data)
    print(f"Repeating task {in_data} because of {e}")
    await activity.parent.close_all()


async def main() -> None:
    golem = GolemNode()
    await golem.event_bus.on(Event, DefaultLogger().on_event)

    async with golem:
        allocation = await golem.create_allocation(1)

        payment_handler = DefaultPaymentHandler(golem, allocation)

        demand = await golem.create_demand(PAYLOAD, allocations=[allocation])

        async def task_stream() -> AsyncIterator[int]:
            while True:
                if task_data:
                    yield task_data.pop(0)
                else:
                    await asyncio.sleep(0.1)

        chain = Chain(
            demand.initial_proposals(),
            Sort(score_proposal, min_elements=10, max_wait=timedelta(seconds=0.1)),
            Map(default_negotiate),
            Map(default_create_agreement),
            Map(default_create_activity),
            Map(prepare_activity),
            ActivityPool(max_size=4),
            Zip(task_stream()),
            Map(execute_task, on_exception=on_exception),  # type: ignore  # unfixable (?)
            Buffer(size=10),
        )

        returned = 0
        async for result in chain:
            returned += 1
            print(f"RESULT {returned}/{task_cnt} {result}")
            if returned == task_cnt:
                break

        print("ALL TASKS DONE")

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
