from typing import Awaitable, AsyncIterator, Callable, Iterable, TypeVar
from random import random
from datetime import timedelta

from golem_api import commands, GolemNode, Payload
from golem_api.low import Activity, Proposal

from golem_api.mid import (
    Chain, SimpleScorer, Map, ExecuteTasks, ActivityPool,
    default_negotiate, default_create_agreement, default_create_activity,
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
    payload: Payload,
    task_data: Iterable[TaskData],
    execute_task: Callable[[Activity, TaskData], Awaitable[TaskResult]],

    max_workers: int = 1,
    prepare_activity: Callable[[Activity], Awaitable[Activity]] = default_prepare_activity,
    score_proposal: Callable[[Proposal], Awaitable[float]] = default_score_proposal,
) -> AsyncIterator[TaskResult]:

    golem = GolemNode()
    golem.event_bus.listen(DefaultLogger().on_event)

    async with golem:
        allocation = await golem.create_allocation(budget)

        payment_manager = DefaultPaymentManager(golem, allocation)
        demand = await golem.create_demand(payload, allocations=[allocation])

        chain = Chain(
            demand.initial_proposals(),
            SimpleScorer(score_proposal, min_proposals=10, max_wait=timedelta(seconds=0.1)),
            Map(default_negotiate),
            Map(default_create_agreement),
            Map(default_create_activity),
            Map(prepare_activity, True),
            ActivityPool(max_size=max_workers),
            ExecuteTasks(execute_task, task_data, max_concurrent=max_workers * 2),
        )

        async for result in chain:
            yield result

        await payment_manager.terminate_agreements()
        await payment_manager.wait_for_invoices()
