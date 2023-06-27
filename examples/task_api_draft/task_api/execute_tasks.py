from datetime import timedelta
from random import random
from typing import AsyncIterator, Awaitable, Callable, Iterable, Optional, Tuple, TypeVar

from golem.resources.activity import Activity, default_prepare_activity
from golem.resources.events.base import Event
from golem.resources.golem_node import GolemNode
from golem.resources.market import (
    Demand,
    Payload,
    Proposal,
    default_create_activity,
    default_create_agreement,
    default_negotiate,
)
from golem.managers import DefaultPaymentManager
from golem.pipeline import Buffer, Chain, Map, Sort, Zip
from golem.utils.logging import DefaultLogger

from .activity_pool import ActivityPool
from .redundance_manager import RedundanceManager
from .task_data_stream import TaskDataStream

TaskData = TypeVar("TaskData")
TaskResult = TypeVar("TaskResult")


async def random_score(proposal: Proposal) -> float:
    return random()


def close_agreement_repeat_task(
    task_stream: TaskDataStream[TaskData],
) -> Callable[[Callable, Tuple[Activity, TaskData], Exception], Awaitable[None]]:
    async def on_exception(
        func: Callable[[Activity, TaskData], Awaitable[TaskResult]],
        args: Tuple[Activity, TaskData],
        e: Exception,
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
            Sort(score_proposal, min_elements=10, max_wait=timedelta(seconds=0.1)),
            Map(default_negotiate),
            Map(default_create_agreement),
            Map(default_create_activity),
            Map(prepare_activity),
            ActivityPool(max_size=max_workers),
            Zip(task_stream),
            Map(
                execute_task,  # type: ignore[arg-type]
                on_exception=close_agreement_repeat_task(task_stream),  # type: ignore[arg-type]
            ),
            Buffer(size=max_workers),
        )
    else:
        min_repeat, min_success = redundance
        redundance_manager = RedundanceManager(
            execute_task, task_stream, min_repeat, min_success, max_workers
        )

        chain = Chain(
            demand.initial_proposals(),
            Sort(score_proposal, min_elements=10, max_wait=timedelta(seconds=0.1)),
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
    score_proposal: Callable[[Proposal], Awaitable[float]] = random_score,
    redundance: Optional[Tuple[int, float]] = None,
) -> AsyncIterator[TaskResult]:
    """High-level entrypoint POC. Interface is expected to change in the near future.

    Yields results of `execute_task` function executed on all elements of `task_data`.

    :param budget: Amount that will be reserved in an :any:`Allocation`.
    :param payload: Specification of the :any:`Demand`.
    :param task_data: Iterable with task input data. In the future, async iterable will also be
        accepted.
        If `redundance` is not None there are two restrictions (both are TODO):

            *   Task data must be hashable
            *   Iterator will be exhausted immediately, so no fancy variable-size iterators
                will work.
    :param execute_task: Async function that will be executed with an :any:`Activity` (based on a
        given `payload`) and a single item from the `task_data` as arguments. Result will be
        returned.
    :param max_workers: How many tasks should be processed at the same time.
    :param prepare_activity: Async function that will be executed once on every :any:`Activity`
        before it will be used for processing `task_data`. Defaults to
        :any:`default_prepare_activity`.
    :param score_proposal: Scoring function that will be passed to :any:`Sort`. Defaults to random.
    :param redundance: Optional tuple (min_provider_cnt, ratio). If passed:

        *   Each task will be repeated on at least `min_provider_cnt` different providers.
        *   Result will be returned when among all results returned by providers there is any
            returned at least `provider_cnt * ratio` times.

        E.g. for (3, 0.7) we might get a result of a task when:

        *   A) 3 providers worked on a task and they all got the same result
        *   B) 4 providers worked on a task and 3 got the same result (because 3/4 >= 0.7)
        *   C) 7 providers worked on a task and 5 got the same result (because 5/7 >= 0.7)

        If `task_data` contains repeating items, result for them will be calculated only once
        (and returned multiple times).


    """

    task_stream = TaskDataStream(task_data)

    golem = GolemNode()
    await golem.event_bus.on(Event, DefaultLogger().on_event)

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
