import asyncio
from datetime import timedelta
from random import random

from yapapi.payload import vm

from golem_api import GolemNode, commands
from golem_api.low import Activity, Proposal

from golem_api.mid import (
    Chain, SimpleScorer, DefaultNegotiator, AgreementCreator, ActivityCreator, Map, TaskExecutor, ActivityPool
)
from golem_api.default_logger import DefaultLogger
from golem_api.default_payment_manager import DefaultPaymentManager


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
    assert activity.idle, f"Got a non-idle activity {activity}"
    command = commands.Run("/bin/echo", ["-n", f"Executed task {task_data} on {activity}"])
    batch = await activity.execute_commands(command)
    await batch.finished

    result = batch.events[-1].stdout
    assert result is not None and "Executed task" in result, f"Got an incorrect result for {task_data}: {result}"

    return result


async def main() -> None:
    golem = GolemNode()
    golem.event_bus.listen(DefaultLogger().on_event)

    async with golem:
        allocation = await golem.create_allocation(1)

        payment_manager = DefaultPaymentManager(golem, allocation)

        payload = await vm.repo(image_hash=IMAGE_HASH)
        demand = await golem.create_demand(payload, allocations=[allocation])

        activity_stream = Chain(
            demand.initial_proposals(),
            SimpleScorer(score_proposal, min_proposals=10, max_wait=timedelta(seconds=0.1)),
            DefaultNegotiator(),
            AgreementCreator(),
            ActivityCreator(),
            Map(prepare_activity, True),
            ActivityPool(),
        )

        task_cnt = 30
        result_cnt = 0

        executor = TaskExecutor(execute_task, activity_stream, list(range(task_cnt)), max_concurrent=3)
        async for result in executor.results():
            result_cnt += 1
            print("RESULT", result)

        print("ALL TASKS DONE")
        assert task_cnt == result_cnt

        await payment_manager.terminate_agreements()
        await payment_manager.wait_for_invoices()


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
