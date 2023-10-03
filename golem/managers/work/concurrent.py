import asyncio
import logging
from typing import Awaitable, Callable, List

from golem.managers.base import Work, WorkManager, WorkResult
from golem.managers.work.mixins import WorkManagerDoWorkMixin, WorkManagerPluginsMixin
from golem.node import GolemNode
from golem.resources import Activity
from golem.utils.asyncio import create_task_with_logging
from golem.utils.logging import get_trace_id_name, trace_span

logger = logging.getLogger(__name__)


class ConcurrentWorkManager(WorkManagerPluginsMixin, WorkManagerDoWorkMixin, WorkManager):
    def __init__(
        self,
        golem: GolemNode,
        get_activity: Callable[[], Awaitable[Activity]],
        size: int,
        *args,
        **kwargs,
    ):
        self._get_activity = get_activity
        self._size = size

        self._queue: asyncio.Queue[Work] = asyncio.Queue()
        self._results: List[WorkResult] = []

        super().__init__(*args, **kwargs)

    @trace_span("Doing work", show_arguments=True, show_results=True, log_level=logging.INFO)
    async def do_work(self, work: Work) -> WorkResult:
        return await self._do_work_with_plugins(self._do_work, work)

    @trace_span("Doing work list", show_arguments=True, show_results=True, log_level=logging.INFO)
    async def do_work_list(self, work_list: List[Work]) -> List[WorkResult]:
        workers = [
            create_task_with_logging(self.worker(), trace_id=get_trace_id_name(self, f"worker-{i}"))
            for i in range(self._size)
        ]
        for work in work_list:
            self._queue.put_nowait(work)
        await self._queue.join()
        [w.cancel() for w in workers]
        await asyncio.gather(*workers, return_exceptions=True)
        return self._results

    async def worker(self):
        while True:
            work = await self._get_work_from_queue()

            result = await self.do_work(work)
            self._queue.task_done()
            self._results.append(result)

    @trace_span(show_results=True)
    async def _get_work_from_queue(self) -> Work:
        return await self._queue.get()
