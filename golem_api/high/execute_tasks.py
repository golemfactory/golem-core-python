from typing import Awaitable, AsyncIterator, Callable, Iterable, TypeVar
from random import random
from datetime import timedelta

from yapapi.payload import vm

from golem_api import GolemNode, commands
from golem_api.low import Activity, Proposal

from golem_api.mid import (
    Chain, SimpleScorer, DefaultNegotiator, AgreementCreator, ActivityCreator, Map, ExecuteTasks, ActivityPool
)
from golem_api.default_logger import DefaultLogger
from golem_api.default_payment_manager import DefaultPaymentManager

TaskData = TypeVar("TaskData")
TaskResult = TypeVar("TaskResult")


async def default_prepare_activity(activity: Activity) -> Activity:
    batch = await activity.execute_commands(commands.Deploy(), commands.Start())
    await batch.wait(timeout=10)
    assert batch.events[-1].result == 'Ok'
    return activity


async def default_score_proposal(proposal: Proposal) -> float:
    return random()


async def execute_tasks(
    *,
    budget: float,
    task_data: Iterable[TaskData],
    execute_task: Callable[[Activity, TaskData], Awaitable[TaskResult]],
    vm_image_hash: str,
    max_workers: int = 1,
    prepare_activity: Callable[[Activity], Awaitable[Activity]] = default_prepare_activity,
    score_proposal: Callable[[Proposal], Awaitable[float]] = default_score_proposal,
) -> AsyncIterator[TaskResult]:
    golem = GolemNode()
    golem.event_bus.listen(DefaultLogger().on_event)

    async with golem:
        allocation = await golem.create_allocation(budget)

        payment_manager = DefaultPaymentManager(golem, allocation)

        payload = await vm.repo(image_hash=vm_image_hash)
        demand = await golem.create_demand(payload, allocations=[allocation])

        chain = Chain(
            demand.initial_proposals(),
            SimpleScorer(score_proposal, min_proposals=10, max_wait=timedelta(seconds=0.1)),
            DefaultNegotiator(),
            AgreementCreator(),
            ActivityCreator(),
            Map(prepare_activity, True),
            ActivityPool(max_size=max_workers),
            ExecuteTasks(execute_task, task_data, max_concurrent=max_workers * 2),
        )

        async for result in chain:
            yield result

        await payment_manager.terminate_agreements()
        await payment_manager.wait_for_invoices()
