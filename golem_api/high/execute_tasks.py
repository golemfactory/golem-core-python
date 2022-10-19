from typing import AsyncIterator, Awaitable, Callable, Iterable, Optional, Tuple, TypeVar
from random import random
from datetime import timedelta

from golem_api import commands, GolemNode, Payload
from golem_api.low import Activity, Demand, Proposal

from golem_api.mid import (
    Buffer, Chain, Map, Zip,
    ActivityPool, SimpleScorer,
    default_negotiate, default_create_agreement, default_create_activity,
)
from golem_api.default_logger import DefaultLogger
from golem_api.default_payment_manager import DefaultPaymentManager

from .task_data_stream import TaskDataStream
from .redundance_manager import RedundanceManager

TaskData = TypeVar("TaskData")
TaskResult = TypeVar("TaskResult")


async def default_prepare_activity(activity: Activity) -> Activity:
    try:
        batch = await activity.execute_commands(commands.Deploy(), commands.Start())
        await batch.wait(timeout=300)
        assert batch.success, batch.events[-1].message
    except Exception:
        await activity.parent.close_all()
        raise
    return activity


async def default_score_proposal(proposal: Proposal) -> float:
    return random()


def close_agreement_repeat_task(
    task_stream: TaskDataStream[TaskData]
) -> Callable[[Callable, Tuple[Activity, TaskData], Exception], Awaitable[None]]:
    async def on_exception(
        func: Callable[[Activity, TaskData], Awaitable[TaskResult]],
        args: Tuple[Activity, TaskData],
        e: Exception
    ) -> None:
        activity, in_data = args
        task_stream.put(in_data)
        print(f"Repeating task {in_data} because of {e}")
        await activity.parent.close_all()
    return on_exception


def get_chain(
    *,
    task_stream: TaskDataStream[TaskData],
    execute_task: Callable[[Activity, TaskData], Awaitable[TaskResult]],
    max_workers: int,
    prepare_activity: Callable[[Activity], Awaitable[Activity]],
    score_proposal: Callable[[Proposal], Awaitable[float]],
    demand: Demand,
    redundance: Optional[Tuple[int, float]],
) -> Chain:
    if redundance is None:
        chain = Chain(
            demand.initial_proposals(),
            SimpleScorer(score_proposal, min_proposals=10, max_wait=timedelta(seconds=0.1)),
            Map(default_negotiate),
            Map(default_create_agreement),
            Map(default_create_activity),
            Map(prepare_activity),
            ActivityPool(max_size=max_workers),
            Zip(task_stream),
            Map(execute_task, on_exception=close_agreement_repeat_task(task_stream)),  # type: ignore  # unfixable (?)
            Buffer(size=max_workers),
        )
    else:
        min_repeat, min_success = redundance
        redundance_manager = RedundanceManager(execute_task, task_stream, min_repeat, min_success, max_workers)

        chain = Chain(
            demand.initial_proposals(),
            SimpleScorer(score_proposal, min_proposals=10, max_wait=timedelta(seconds=0.1)),
            redundance_manager.filter_providers,
            Map(default_negotiate),
            Map(default_create_agreement),
            Map(default_create_activity),
            Map(prepare_activity),
            ActivityPool(max_size=max_workers),
            redundance_manager.execute_tasks,
        )
    return chain


async def execute_tasks(
    *,
    budget: float,
    payload: Payload,
    task_data: Iterable[TaskData],
    execute_task: Callable[[Activity, TaskData], Awaitable[TaskResult]],

    max_workers: int = 1,
    prepare_activity: Callable[[Activity], Awaitable[Activity]] = default_prepare_activity,
    score_proposal: Callable[[Proposal], Awaitable[float]] = default_score_proposal,

    redundance: Optional[Tuple[int, float]] = None,
) -> AsyncIterator[TaskResult]:

    task_stream = TaskDataStream(task_data)

    golem = GolemNode()
    golem.event_bus.listen(DefaultLogger().on_event)

    async with golem:
        allocation = await golem.create_allocation(budget)

        payment_manager = DefaultPaymentManager(golem, allocation)
        demand = await golem.create_demand(payload, allocations=[allocation])

        chain = get_chain(
            task_stream=task_stream,
            execute_task=execute_task,
            max_workers=max_workers,
            prepare_activity=prepare_activity,
            score_proposal=score_proposal,
            demand=demand,
            redundance=redundance,
        )

        returned = 0
        async for result in chain:
            yield result
            returned += 1
            if task_stream.in_stream_empty and returned == task_stream.task_cnt:
                break

        await payment_manager.terminate_agreements()
        await payment_manager.wait_for_invoices()
