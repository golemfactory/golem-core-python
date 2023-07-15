import asyncio
import logging
from typing import List

from golem.managers.base import DoWorkCallable, Work, WorkManager, WorkResult
from golem.managers.work.mixins import WorkManagerPluginsMixin
from golem.node import GolemNode
from golem.utils.logging import trace_span

logger = logging.getLogger(__name__)


class AsynchronousWorkManager(WorkManagerPluginsMixin, WorkManager):
    def __init__(self, golem: GolemNode, do_work: DoWorkCallable, *args, **kwargs):
        self._do_work = do_work

        super().__init__(*args, **kwargs)

    @trace_span(show_arguments=True, show_results=True)
    async def do_work(self, work: Work) -> WorkResult:
        result = await self._do_work_with_plugins(self._do_work, work)
        logger.info(f"Work `{work}` completed")
        return result

    @trace_span(show_arguments=True, show_results=True)
    async def do_work_list(self, work_list: List[Work]) -> List[WorkResult]:
        results = await asyncio.gather(*[self.do_work(work) for work in work_list])
        return results
