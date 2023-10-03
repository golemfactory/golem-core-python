import logging
from typing import Awaitable, Callable, List

from golem.managers.base import Work, WorkManager, WorkResult
from golem.managers.work.mixins import WorkManagerDoWorkMixin, WorkManagerPluginsMixin
from golem.node import GolemNode
from golem.resources import Activity
from golem.utils.logging import trace_span

logger = logging.getLogger(__name__)


class SequentialWorkManager(WorkManagerPluginsMixin, WorkManagerDoWorkMixin, WorkManager):
    def __init__(
        self, golem: GolemNode, get_activity: Callable[[], Awaitable[Activity]], *args, **kwargs
    ):
        self._get_activity = get_activity

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
