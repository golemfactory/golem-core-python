import asyncio
from collections import Counter, defaultdict
from typing import (
    AsyncIterator,
    Awaitable,
    Callable,
    DefaultDict,
    List,
    Optional,
    Set,
    Tuple,
    TypeVar,
)

from golem.resources import Activity, Proposal

from .task_data_stream import TaskDataStream

TaskData = TypeVar("TaskData")
TaskResult = TypeVar("TaskResult")
ProviderId = str


class RedundanceManager:
    def __init__(
        self,
        execute_task: Callable[[Activity, TaskData], Awaitable[TaskResult]],
        task_stream: TaskDataStream[TaskData],
        min_repeat: int,
        min_success: float,
        worker_cnt: int,
    ):
        self.task_callable = execute_task
        self.remaining_tasks = task_stream.all_remaining_tasks()
        self.min_repeat = min_repeat
        self.min_success = min_success
        self.worker_cnt = worker_cnt

        self._partial_results: List[Tuple[TaskData, TaskResult]] = []
        self._provider_tasks: DefaultDict[ProviderId, List[TaskData]] = defaultdict(list)
        self._useless_providers: Set[ProviderId] = set()

        self._activity_stream_lock = asyncio.Lock()
        self._workers: List[asyncio.Task] = []
        self._results_queue: asyncio.Queue[TaskResult] = asyncio.Queue()

    async def filter_providers(
        self, proposal_stream: AsyncIterator[Proposal]
    ) -> AsyncIterator[Proposal]:
        """Filter out proposals from providers who already processed all remaining tasks."""
        while self.remaining_tasks:
            proposal = await proposal_stream.__anext__()
            provider_id = (await proposal.get_data()).issuer_id
            if provider_id in self._useless_providers:
                # Skipping proposal from {provider_id} because they have already processed all the
                # tasks
                pass
            else:
                yield proposal

        #   TODO: We wait here forever because Map, Zip etc) don't work with finite streams.
        #         https://github.com/golemfactory/golem-core-python/issues/8
        print("All tasks done - no more proposals will be processed")
        await asyncio.Future()

    async def execute_tasks(
        self, activity_stream: AsyncIterator[Awaitable[Activity]]
    ) -> AsyncIterator[TaskResult]:
        self._workers = [
            asyncio.create_task(self._worker_task(activity_stream)) for _ in range(self.worker_cnt)
        ]
        for task_data in self.remaining_tasks.copy():
            yield await self._results_queue.get()  # type: ignore  # mypy, why?

    async def _worker_task(self, activity_stream: AsyncIterator[Awaitable[Activity]]) -> None:
        while self.remaining_tasks:
            async with self._activity_stream_lock:
                activity_awaitable = await activity_stream.__anext__()
            activity = await activity_awaitable

            provider_id = (await activity.parent.parent.get_data()).issuer_id
            assert provider_id is not None  # mypy
            task_data = self._task_for_provider(provider_id)
            if task_data is None:
                self._useless_providers.add(provider_id)
                await activity.parent.close_all()
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
                return task_data  # type: ignore
        return None

    def _process_task_result(self, this_task_data: TaskData, this_task_result: TaskResult) -> None:
        if this_task_data not in self.remaining_tasks:
            #   We processed this task more times than necessary.
            #   This is possible because now in _task_for_provider we don't care if given task is
            #   already being processed in some other worker or not. Also: this might help speed
            #   things up, so is not really a bug/problem, but rather a decision.
            return

        self._partial_results.append((this_task_data, this_task_result))  # type: ignore
        task_results = [
            task_result
            for task_data, task_result in self._partial_results
            if task_data == this_task_data
        ]

        print(f"Current task {this_task_data} results: {Counter(task_results).most_common()}")

        cnt = len(task_results)
        if cnt < self.min_repeat:
            return

        #   TODO: this assumes TaskResult is hashable
        most_common = Counter(task_results).most_common()[0][0]
        if (task_results.count(most_common) / cnt) < self.min_success:
            return

        self.remaining_tasks.remove(this_task_data)  # type: ignore
        self._results_queue.put_nowait(most_common)
