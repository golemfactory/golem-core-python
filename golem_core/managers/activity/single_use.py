import logging
from contextlib import asynccontextmanager
from typing import Awaitable, Callable, Optional

from golem_core.core.activity_api import Activity
from golem_core.core.events import EventBus
from golem_core.core.market_api import Agreement
from golem_core.managers.activity.defaults import (
    default_on_activity_start,
    default_on_activity_stop,
)
from golem_core.managers.agreement import AgreementReleased
from golem_core.managers.base import ActivityManager, Work, WorkContext, WorkResult

logger = logging.getLogger(__name__)
print(logger)


class SingleUseActivityManager(ActivityManager):
    def __init__(
        self,
        get_agreement: Callable[[], Awaitable[Agreement]],
        event_bus: EventBus,
        on_activity_start: Optional[
            Callable[[WorkContext], Awaitable[None]]
        ] = default_on_activity_start,
        on_activity_stop: Optional[
            Callable[[WorkContext], Awaitable[None]]
        ] = default_on_activity_stop,
    ):
        self._get_agreement = get_agreement
        self._event_bus = event_bus
        self._on_activity_start = on_activity_start
        self._on_activity_stop = on_activity_stop

    @asynccontextmanager
    async def _prepare_activity(self) -> Activity:
        logger.debug("Calling `_prepare_activity`...")

        while True:
            logger.debug(f"Getting agreement...")

            agreement = await self._get_agreement()

            logger.debug(f"Getting agreement done with `{agreement}`")

            try:
                logger.debug(f"Creating activity...")

                activity = await agreement.create_activity()

                logger.debug(f"Creating activity done")

                logger.debug(f"Yielding activity...")

                yield activity

                logger.debug(f"Yielding activity done")

                break
            except Exception as e:
                logger.debug(
                    f"Creating activity failed with {e}, but will be retried with new agreement"
                )
            finally:
                event = AgreementReleased(agreement)

                logger.debug(f"Releasing agreement by emitting `{event}`...")

                self._event_bus.emit(event)

                logger.debug(f"Releasing agreement by emitting `{event}` done")

        logger.debug("Calling `_prepare_activity` done")

    async def do_work(self, work: Work) -> WorkResult:
        logger.debug("Calling `do_work`...")

        async with self._prepare_activity() as activity:
            work_context = WorkContext(activity)

            if self._on_activity_start:
                logger.debug("Calling `on_activity_start`...")

                await self._on_activity_start(work_context)

                logger.debug("Calling `on_activity_start` done")

            try:
                logger.debug("Calling `work`...")
                work_result = await work(work_context)
            except Exception as e:
                logger.debug(f"Calling `work` done with exception `{e}`")
                work_result = WorkResult(exception=e)
            else:
                if isinstance(work_result, WorkResult):
                    logger.debug(f"Calling `work` done with explicit result `{work_result}`")
                else:
                    logger.debug(f"Calling `work` done with implicit result `{work_result}`")

                    work_result = WorkResult(result=work_result)

            if self._on_activity_stop:
                logger.debug("Calling `on_activity_stop`...")

                await self._on_activity_stop(work_context)

                logger.debug("Calling `on_activity_stop` done")

            if not activity.destroyed:
                logger.warning(
                    "SingleUseActivityManager expects that activity will be terminated"
                    " after its work is finished. Looks like you forgot calling"
                    " `context.terminate()` in custom `on_activity_end` callback."
                )

        logger.debug("Calling `do_work` done")

        return work_result
