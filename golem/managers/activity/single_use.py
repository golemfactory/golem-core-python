import logging
from contextlib import asynccontextmanager
from typing import Awaitable, Callable, Optional

from golem.managers.activity.defaults import default_on_activity_start, default_on_activity_stop
from golem.managers.agreement import AgreementReleased
from golem.managers.base import ActivityManager, Work, WorkContext, WorkResult
from golem.node import GolemNode
from golem.resources import Activity, Agreement

logger = logging.getLogger(__name__)


class SingleUseActivityManager(ActivityManager):
    def __init__(
        self,
        golem: GolemNode,
        get_agreement: Callable[[], Awaitable[Agreement]],
        on_activity_start: Optional[
            Callable[[WorkContext], Awaitable[None]]
        ] = default_on_activity_start,
        on_activity_stop: Optional[
            Callable[[WorkContext], Awaitable[None]]
        ] = default_on_activity_stop,
    ):
        self._get_agreement = get_agreement
        self._event_bus = golem.event_bus
        self._on_activity_start = on_activity_start
        self._on_activity_stop = on_activity_stop

    @asynccontextmanager
    async def _prepare_activity(self) -> Activity:
        while True:
            logger.debug("Getting agreement...")

            agreement = await self._get_agreement()

            logger.debug(f"Getting agreement done with `{agreement}`")

            try:
                logger.debug("Creating activity...")

                activity = await agreement.create_activity()

                logger.debug(f"Creating activity done with `{activity}`")
                logger.info(f"Activity `{activity}` created")

                logger.debug("Yielding activity...")

                yield activity

                logger.debug("Yielding activity done")

                break
            except Exception:
                logger.exception("Creating activity failed, but will be retried with new agreement")
            finally:
                event = AgreementReleased(agreement)

                logger.debug(f"Releasing agreement by emitting `{event}`...")

                await self._event_bus.emit(event)

                logger.debug(f"Releasing agreement by emitting `{event}` done")

    async def do_work(self, work: Work) -> WorkResult:
        logger.debug(f"Doing work `{work}`...")

        async with self._prepare_activity() as activity:
            work_context = WorkContext(activity)

            if self._on_activity_start:
                logger.debug("Calling `on_activity_start`...")

                await self._on_activity_start(work_context)

                logger.debug("Calling `on_activity_start` done")

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

            if self._on_activity_stop:
                logger.debug(f"Calling `on_activity_stop` on activity `{activity}`...")

                await self._on_activity_stop(work_context)

                logger.debug(f"Calling `on_activity_stop` on activity `{activity}` done")

            if activity.destroyed:
                logger.info(f"Activity `{activity}` destroyed")
            else:
                logger.warning(
                    "SingleUseActivityManager expects that activity will be terminated"
                    " after its work is finished. Looks like you forgot calling"
                    " `context.terminate()` in custom `on_activity_end` callback."
                )

        logger.debug(f"Doing work `{work}` done")

        return work_result
