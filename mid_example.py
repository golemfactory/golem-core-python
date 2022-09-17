import asyncio
from datetime import timedelta
from random import random

from yapapi.payload import vm

from golem_api import GolemNode, commands
from golem_api.low import Activity, DebitNote, Invoice, Proposal

from golem_api.mid import Chain, SimpleScorer, DefaultNegotiator, AgreementCreator, ActivityCreator, Map, TaskExecutor
from golem_api.default_logger import DefaultLogger
from golem_api.default_payment_manager import DefaultPaymentManager
from golem_api.events import NewResource


IMAGE_HASH = "9a3b5d67b0b27746283cb5f287c13eab1beaa12d92a9f536b747c7ae"


async def score_proposal(proposal: Proposal) -> float:
    return random()


async def prepare_activity(activity: Activity) -> Activity:
    batch = await activity.execute_commands(
        commands.Deploy(),
        commands.Start(),
        commands.Run("/bin/echo", ["-n", f"ACTIVITY {activity.id} IS READY"]),
    )
    await batch.finished
    print(batch.events[-1].stdout)
    return activity


async def execute_task(activity: Activity, task_data: int) -> str:
    command = commands.Run("/bin/echo", ["-n", f"Executed task {task_data} on {activity}"])
    batch = await activity.execute_commands(command)
    await batch.finished
    return batch.events[-1].stdout  # type: ignore


async def main() -> None:
    golem = GolemNode()
    golem.event_bus.listen(DefaultLogger().on_event)

    async with golem:
        allocation = await golem.create_allocation(1)

        payment_manager = DefaultPaymentManager(allocation)
        golem.event_bus.resource_listen(payment_manager.on_invoice, [NewResource], [Invoice])
        golem.event_bus.resource_listen(payment_manager.on_debit_note, [NewResource], [DebitNote])

        payload = await vm.repo(image_hash=IMAGE_HASH)
        demand = await golem.create_demand(payload, allocations=[allocation])

        #   Create a stream of awaitables returning ready-to-use activities
        activity_stream = Chain(
            demand.initial_proposals(),
            SimpleScorer(score_proposal, min_proposals=10, max_wait=timedelta(seconds=0.1)),
            DefaultNegotiator(),
            AgreementCreator(),
            ActivityCreator(),
            Map(prepare_activity, True),
        )

        executor = TaskExecutor(execute_task, activity_stream, list(range(5)))
        result: str
        async for result in executor.results():
            print(result)


if __name__ == '__main__':
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
