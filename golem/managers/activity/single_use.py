import logging
from contextlib import asynccontextmanager
from typing import Awaitable, Callable

from golem.managers.activity.mixins import ActivityPrepareReleaseMixin
from golem.managers.base import ActivityManager, Work, WorkContext, WorkResult
from golem.node import GolemNode
from golem.resources import Activity, Agreement
from golem.utils.logging import trace_span

logger = logging.getLogger(__name__)


class SingleUseActivityManager(ActivityPrepareReleaseMixin, ActivityManager):
    def __init__(
        self, golem: GolemNode, get_agreement: Callable[[], Awaitable[Agreement]], *args, **kwargs
    ):
        self._get_agreement = get_agreement
        self._event_bus = golem.event_bus

        super().__init__(*args, **kwargs)

    @asynccontextmanager
    async def _prepare_single_use_activity(self) -> Activity:
        while True:
            agreement = await self._get_agreement()
            try:
                activity = await self._prepare_activity(agreement)
                logger.info(f"Activity `{activity}` created")
                yield activity
                await self._release_activity(activity)
                break
            except Exception:
                logger.exception("Creating activity failed, but will be retried with new agreement")

    @trace_span()
    async def do_work(self, work: Work) -> WorkResult:
        async with self._prepare_single_use_activity() as activity:
            work_context = WorkContext(activity)
            try:
                work_result = await work(work_context)
            except Exception as e:
                work_result = WorkResult(exception=e)
            else:
                if not isinstance(work_result, WorkResult):
                    work_result = WorkResult(result=work_result)
        return work_result
