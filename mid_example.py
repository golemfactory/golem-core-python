import asyncio
from datetime import timedelta
from random import random

from yapapi.payload import vm

from golem_api import GolemNode, commands
from golem_api.low import Activity, Proposal

from golem_api.mid import (
    Chain, SimpleScorer, DefaultNegotiator, AgreementCreator, ActivityCreator, Map, ExecuteTasks, ActivityPool
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
    await batch.wait(timeout=10)
    assert batch.events[-1].stdout is not None and "IS READY" in batch.events[-1].stdout, "Prepare activity failed"
    print(batch.events[-1].stdout)
    return activity


async def execute_task(activity: Activity, task_data: int) -> str:
    assert activity.idle, f"Got a non-idle activity {activity}"
    command = commands.Run("/bin/echo", ["-n", f"Executed task {task_data} on {activity}"])
    batch = await activity.execute_commands(command)
    await batch.wait(timeout=3)

    result = batch.events[-1].stdout
    assert result is not None and "Executed task" in result, f"Got an incorrect result for {task_data}: {result}"

    # if random() > 0.98:
    #     1 / 0

    return result


async def main() -> None:
    golem = GolemNode()
    golem.event_bus.listen(DefaultLogger().on_event)

    async with golem:
        allocation = await golem.create_allocation(1)

        payment_manager = DefaultPaymentManager(golem, allocation)

        payload = await vm.repo(image_hash=IMAGE_HASH)
        demand = await golem.create_demand(payload, allocations=[allocation])

        task_cnt = 10
        task_data = list(range(task_cnt))

        chain = Chain(
            demand.initial_proposals(),
            SimpleScorer(score_proposal, min_proposals=10, max_wait=timedelta(seconds=0.1)),
            DefaultNegotiator(),
            AgreementCreator(),
            ActivityCreator(),
            Map(prepare_activity, True),
            ActivityPool(max_size=4),
            ExecuteTasks(execute_task, task_data),
        )

        result_cnt = 0
        async for result in chain:
            result_cnt += 1
            print(f"RESULT {result_cnt}/{task_cnt} {result}")

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
