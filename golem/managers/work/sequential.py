import logging
from typing import List

from golem.managers.base import DoWorkCallable, Work, WorkManager, WorkResult
from golem.managers.work.mixins import WorkManagerPluginsMixin
from golem.node import GolemNode
from golem.utils.logging import trace_span

logger = logging.getLogger(__name__)


class SequentialWorkManager(WorkManagerPluginsMixin, WorkManager):
    def __init__(self, golem: GolemNode, do_work: DoWorkCallable, *args, **kwargs):
        self._do_work = do_work

        super().__init__(*args, **kwargs)

    @trace_span("Doing work", show_arguments=True, show_results=True, log_level=logging.INFO)
    async def do_work(self, work: Work) -> WorkResult:
        return await self._do_work_with_plugins(self._do_work, work)

    @trace_span("Doing work list", show_arguments=True, show_results=True, log_level=logging.INFO)
    async def do_work_list(self, work_list: List[Work]) -> List[WorkResult]:
        results = []

        for i, work in enumerate(work_list):
            results.append(await self.do_work(work))

        return results
