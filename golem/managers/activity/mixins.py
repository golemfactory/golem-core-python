import logging
from typing import Awaitable, Callable, Optional

from golem.event_bus.base import EventBus
from golem.managers.activity.defaults import default_on_activity_start, default_on_activity_stop
from golem.managers.base import WorkContext
from golem.resources import Activity
from golem.utils.logging import trace_span

logger = logging.getLogger(__name__)


class ActivityWrapper:
    def __init__(self, activity: Activity) -> None:
        self._activity = activity

    def __getattr__(self, item):
        return getattr(self._activity, item)


class ActivityPrepareReleaseMixin:
    _event_bus: EventBus

    def __init__(
        self,
        on_activity_start: Optional[
            Callable[[WorkContext], Awaitable[None]]
        ] = default_on_activity_start,
        on_activity_stop: Optional[
            Callable[[WorkContext], Awaitable[None]]
        ] = default_on_activity_stop,
        *args,
        **kwargs,
    ) -> None:
        self._on_activity_start = on_activity_start
        self._on_activity_stop = on_activity_stop

        super().__init__(*args, **kwargs)

    @trace_span(show_arguments=True, show_results=True)
    async def _prepare_activity(self, agreement) -> Activity:
        activity = await agreement.create_activity()
        logger.info(f"Activity `{activity}` created")
        work_context = WorkContext(activity)
        if self._on_activity_start:
            await self._on_activity_start(work_context)
        return activity

    @trace_span(show_arguments=True)
    async def _release_activity(self, activity: Activity) -> None:
        if self._on_activity_stop:
            work_context = WorkContext(activity)
            await self._on_activity_stop(work_context)

        if activity.destroyed:
            logger.info(f"Activity `{activity}` destroyed")
        else:
            logger.warning(
                "ActivityManager expects that activity will be terminated"
                " before activity is released. Looks like you forgot calling"
                " `context.terminate()` in custom `on_activity_end` callback."
            )
