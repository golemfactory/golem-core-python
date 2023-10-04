import logging
from typing import Awaitable, Callable

from golem.managers.activity.mixins import ActivityPrepareReleaseMixin, ActivityWrapper
from golem.managers.base import ActivityManager
from golem.node import GolemNode
from golem.resources import Activity, Agreement
from golem.utils.logging import trace_span

logger = logging.getLogger(__name__)


@Activity.register
class SingleUseActivity(ActivityWrapper):
    def __init__(
        self,
        activity,
        release_activity_func,
    ) -> None:
        super().__init__(activity)
        self._release_activity_func = release_activity_func

    async def destroy(self) -> None:
        await self._release_activity_func(self._activity)


class SingleUseActivityManager(ActivityPrepareReleaseMixin, ActivityManager):
    def __init__(
        self, golem: GolemNode, get_agreement: Callable[[], Awaitable[Agreement]], *args, **kwargs
    ):
        self._get_agreement = get_agreement
        self._event_bus = golem.event_bus

        super().__init__(*args, **kwargs)

    @trace_span(show_arguments=True, show_results=True)
    async def get_activity(self) -> Activity:
        while True:
            agreement = await self._get_agreement()
            try:
                activity = await self._prepare_activity(agreement)

                logger.info(f"Activity `{activity}` created")
                # mypy doesn't support `ABCMeta.register` https://github.com/python/mypy/issues/2922
                return SingleUseActivity(
                    activity, self._release_activity
                )  # type: ignore[return-value]

            except Exception:
                logger.exception("Creating activity failed, but will be retried with new agreement")
