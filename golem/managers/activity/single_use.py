import logging
from contextlib import asynccontextmanager
from typing import Awaitable, Callable

from golem.managers.activity.mixins import ActivityPrepareReleaseMixin
from golem.managers.base import ActivityManager, Work, WorkContext, WorkResult
from golem.node import GolemNode
from golem.resources import Activity, Agreement

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
            logger.debug("Getting agreement...")

            agreement = await self._get_agreement()

            logger.debug(f"Getting agreement done with `{agreement}`")

            try:
                logger.debug("Creating activity...")

                activity = await self._prepare_activity(agreement)

                logger.debug(f"Creating activity done with `{activity}`")
                logger.info(f"Activity `{activity}` created")

                logger.debug("Yielding activity...")

                yield activity

                await self._release_activity(activity)

                logger.debug("Yielding activity done")

                break
            except Exception:
                logger.exception("Creating activity failed, but will be retried with new agreement")

    async def do_work(self, work: Work) -> WorkResult:
        logger.debug(f"Doing work `{work}`...")

        async with self._prepare_single_use_activity() as activity:
            work_context = WorkContext(activity)

            try:
                logger.debug(f"Calling `{work}`...")
                work_result = await work(work_context)
            except Exception as e:
                logger.debug(f"Calling `{work}` done with exception `{e}`")
                work_result = WorkResult(exception=e)
            else:
                if isinstance(work_result, WorkResult):
                    logger.debug(f"Calling `{work}` done with explicit result `{work_result}`")
                else:
                    logger.debug(f"Calling `{work}` done with implicit result `{work_result}`")

                    work_result = WorkResult(result=work_result)

        logger.debug(f"Doing work `{work}` done")

        return work_result
