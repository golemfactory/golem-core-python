import asyncio
from collections import Counter, defaultdict
from typing import (
    Awaitable, AsyncIterator, Callable, DefaultDict, Generic, Iterable, List, Optional, Set, Tuple, TypeVar
)
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

    def remaining_tasks(self) -> List[TaskData]:
        new_tasks = list(self.in_stream)
        self.task_cnt += len(new_tasks)
        self.in_stream_empty = True
        return new_tasks + self.repeated


async def default_prepare_activity(activity: Activity) -> Activity:
    try:
        batch = await activity.execute_commands(commands.Deploy(), commands.Start())
        await batch.wait(timeout=300)
        assert batch.success, batch.events[-1].message
    except Exception:
        await activity.destroy()
        await activity.parent.terminate()
        raise
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


class RedundanceManager:
    def __init__(
        self,
        execute_task: Callable[[Activity, TaskData], Awaitable[TaskResult]],
        task_stream: TaskStream[TaskData],
        min_repeat: int,
        min_success: float,
        worker_cnt: int,
    ):
        self.task_callable = execute_task
        self.remaining_tasks = task_stream.remaining_tasks()
        self.min_repeat = min_repeat
        self.min_success = min_success
        self.worker_cnt = worker_cnt

        self._partial_results: List[Tuple[TaskData, TaskResult]] = []
        self._provider_tasks: DefaultDict[ProviderId, List[TaskData]] = defaultdict(list)
        self._useless_providers: Set[ProviderId] = set()

        self._activity_stream_lock = asyncio.Lock()
        self._workers: List[asyncio.Task] = []
        self._results_queue: asyncio.Queue[TaskResult] = asyncio.Queue()

    async def filter_providers(self, proposal_stream: AsyncIterator[Proposal]) -> AsyncIterator[Proposal]:
        """Filter out proposals from providers who already processed all remaining tasks."""
        while self.remaining_tasks:
            proposal = await proposal_stream.__anext__()
            provider_id = (await proposal.get_data()).issuer_id
            if provider_id in self._useless_providers:
                #   Skipping proposal from {provider_id} because they have already processed all the tasks
                pass
            else:
                yield proposal

        #   TODO: We wait here forever because Map, Zip etc) don't work with finite streams.
        #         This will be improved in the future.
        print("All tasks done - no more proposals will be processed")
        await asyncio.Future()

    async def execute_tasks(
        self, activity_stream: AsyncIterator[Awaitable[Activity]]
    ) -> AsyncIterator[TaskResult]:
        self._workers = [asyncio.create_task(self._execute_tasks(activity_stream)) for _ in range(self.worker_cnt)]
        for task_data in self.remaining_tasks.copy():
            yield await self._results_queue.get()  # type: ignore  # mypy, why?

    async def _execute_tasks(self, activity_stream: AsyncIterator[Awaitable[Activity]]) -> None:
        while self.remaining_tasks:
            async with self._activity_stream_lock:
                activity_awaitable = await activity_stream.__anext__()
            activity = await activity_awaitable

            provider_id = (await activity.parent.parent.get_data()).issuer_id
            assert provider_id is not None  # mypy
            task_data = self._task_for_provider(provider_id)
            if task_data is None:
                self._close_useless_activity(activity)
                self._useless_providers.add(provider_id)
                continue

            try:
                self._provider_tasks[provider_id].append(task_data)
                task_result = await self.task_callable(activity, task_data)
            except Exception:
                self._provider_tasks[provider_id].remove(task_data)
                self._close_useless_activity(activity)
                continue

            self._process_task_result(task_data, task_result)

    def _task_for_provider(self, provider_id: str) -> Optional[TaskData]:
        for task_data in self.remaining_tasks:
            if task_data not in self._provider_tasks[provider_id]:
                return task_data
        return None

    def _close_useless_activity(self, activity: Activity) -> None:
        # print(f"{activity} is useless")

        async def close() -> None:
            #   TODO: this will be probably moved to `Agreement.clear` or something like this
            try:
                await activity.destroy()
            except Exception:
                pass
            try:
                await activity.parent.terminate()
            except Exception:
                pass

        asyncio.create_task(close())

    def _process_task_result(self, this_task_data: TaskData, this_task_result: TaskResult) -> None:
        if this_task_data not in self.remaining_tasks:
            #   We processed this task more times than necessary.
            #   This is possible because now in _task_for_provider we don't care if given task is already being
            #   processed in some other task or not. Also: this might help speed things up, so is not really
            #   a bug/problem, but rather a decision.
            return

        self._partial_results.append((this_task_data, this_task_result))
        task_results = [task_result for task_data, task_result in self._partial_results if task_data == this_task_data]

        print(f"Current task {this_task_data} results: {Counter(task_results).most_common()}")

        cnt = len(task_results)
        if cnt < self.min_repeat:
            return

        #   TODO: this assumes TaskResult is hashable
        most_common = Counter(task_results).most_common()[0][0]
        if (task_results.count(most_common) / cnt) < self.min_success:
            return

        self.remaining_tasks.remove(this_task_data)
        self._results_queue.put_nowait(most_common)


def get_chain(
    *,
    task_stream: TaskStream[TaskData],
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
            Buffer(size=max_workers + 1),
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
