import asyncio
import logging
from typing import List

from golem.managers.base import DoWorkCallable, Work, WorkManager, WorkResult
from golem.managers.work.mixins import WorkManagerPluginsMixin
from golem.node import GolemNode
from golem.utils.asyncio import create_task_with_logging
from golem.utils.logging import trace_span

logger = logging.getLogger(__name__)


class ConcurrentWorkManager(WorkManagerPluginsMixin, WorkManager):
    def __init__(self, golem: GolemNode, do_work: DoWorkCallable, size: int, *args, **kwargs):
        self._do_work = do_work
        self._size = size

        self._queue: asyncio.Queue[Work] = asyncio.Queue()
        self._results: List[WorkResult] = []

        super().__init__(*args, **kwargs)

    @trace_span(show_arguments=True, show_results=True)
    async def do_work(self, work: Work) -> WorkResult:
        result = await self._do_work_with_plugins(self._do_work, work)
        logger.info(f"Work `{work}` completed")
        return result

    @trace_span(show_arguments=True, show_results=True)
    async def do_work_list(self, work_list: List[Work]) -> List[WorkResult]:
        workers = [create_task_with_logging(self.worker()) for _ in range(self._size)]
        for work in work_list:
            self._queue.put_nowait(work)
        await self._queue.join()
        [w.cancel() for w in workers]
        await asyncio.gather(*workers, return_exceptions=True)
        return self._results

    async def worker(self):
        while True:
            work = await self._queue.get()
            result = await self.do_work(work)
            self._queue.task_done()
            self._results.append(result)
