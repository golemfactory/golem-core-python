import asyncio
from collections import Counter, defaultdict
from typing import Awaitable, AsyncIterator, Callable, Dict, Generic, Iterable, List, Optional, Tuple, TypeVar
from random import random
from datetime import timedelta

from golem_api import commands, GolemNode, Payload
from golem_api.low import Activity, Proposal

from golem_api.mid import (
    Buffer, Chain, Map, Zip,
    ActivityPool, SimpleScorer,
    default_negotiate, default_create_agreement, default_create_activity,
)
from golem_api.default_logger import DefaultLogger
from golem_api.default_payment_manager import DefaultPaymentManager

TaskData = TypeVar("TaskData")
TaskResult = TypeVar("TaskResult")
ProviderId = str


class TaskStream(Generic[TaskData]):
    def __init__(self, in_stream: Iterable[TaskData]):
        #   TODO: in_stream could be AsyncIterable as well
        self.in_stream = iter(in_stream)
        self.task_cnt = 0
        self.in_stream_empty = False
        self.repeated: List[TaskData] = []

    def put(self, value: TaskData) -> None:
        self.repeated.append(value)

    def __aiter__(self) -> "TaskStream":
        return self

    async def __anext__(self) -> TaskData:
        while True:
            if self.repeated:
                return self.repeated.pop(0)
            elif not self.in_stream_empty:
                try:
                    val = next(self.in_stream)
                    self.task_cnt += 1
                    return val
                except StopIteration:
                    self.in_stream_empty = True
            await asyncio.sleep(0.1)


async def default_prepare_activity(activity: Activity) -> Activity:
    batch = await activity.execute_commands(commands.Deploy(), commands.Start())
    await batch.wait(timeout=10)
    assert batch.success, batch.events[-1].message
    return activity


async def default_score_proposal(proposal: Proposal) -> float:
    return random()


def close_agreement_repeat_task(
    task_stream: TaskStream[TaskData]
) -> Callable[[Callable, Tuple[Activity, TaskData], Exception], Awaitable[None]]:
    async def on_exception(
        func: Callable[[Activity, TaskData], Awaitable[TaskResult]],
        args: Tuple[Activity, TaskData],
        e: Exception
    ) -> None:
        activity, in_data = args
        task_stream.put(in_data)
        print(f"Repeating task {in_data} because of {e}")
        await activity.destroy()
        await activity.parent.terminate()
    return on_exception


class RepeatRequired(Exception):
    pass


class RedundanceManager:
    def __init__(
        self,
        execute_task: Callable[[Activity, TaskData], Awaitable[TaskResult]],
        repeat_task: Callable[[TaskData], None],
        min_repeat: int,
        min_success: float,
    ):
        self.task_callable = execute_task
        self.repeat_task_callable = repeat_task
        self.min_repeat = min_repeat
        self.min_success = min_success

        self._results: Dict[ProviderId, List[Tuple(TaskData, TaskResult)]] = defaultdict(list)

    async def execute_task(self, activity: Activity, task_data: TaskData):
        task_result = await self.task_callable(activity, task_data)
        provider_id = (await activity.parent.parent.get_data()).issuer_id
        self._results[provider_id].append((task_data, task_result))

        final_result = self._get_final_result(task_data)
        if final_result is None:
            raise RepeatRequired

        return final_result

    async def on_exception(self, func, args, exc):
        activity, task_data = args
        self.repeat_task_callable(task_data)
        if not isinstance(exc, RepeatRequired):
            await activity.destroy()
            await activity.parent.terminate()

    def _get_final_result(self, this_task_data: TaskData):
        task_results = []
        for provider_results in self._results.values():
            task_results += [task_result for task_data, task_result in provider_results if task_data == this_task_data]

        print("TASK RESULTS", task_results)

        cnt = len(task_results)
        if cnt < self.min_repeat:
            return None

        #   TODO: this assumes TaskResult is hashable
        most_common = Counter(task_results).most_common()[0][0]
        if (task_results.count(most_common) / cnt) < self.min_success:
            return None

        return most_common


def get_chain(
    *,
    task_stream,
    execute_task,
    max_workers,
    prepare_activity,
    score_proposal,
    demand,
    redundance
):
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
            Buffer(size=max_workers + 1),
        )
    else:
        min_repeat, min_success = redundance
        redundance_manager = RedundanceManager(execute_task, task_stream.put, min_repeat, min_success)

        chain = Chain(
            demand.initial_proposals(),
            SimpleScorer(score_proposal, min_proposals=10, max_wait=timedelta(seconds=0.1)),
            Map(default_negotiate),
            Map(default_create_agreement),
            Map(default_create_activity),
            Map(prepare_activity),
            ActivityPool(max_size=max_workers),
            Zip(task_stream),
            Map(redundance_manager.execute_task, on_exception=redundance_manager.on_exception),
            Buffer(size=max_workers + 1),
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

    redundance: Optional[float] = None,
) -> AsyncIterator[TaskResult]:

    task_stream = TaskStream(task_data)

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
