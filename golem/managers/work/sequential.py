import logging
from typing import List

from golem.managers.base import (
    WORK_PLUGIN_FIELD_NAME,
    DoWorkCallable,
    ManagerPluginsMixin,
    Work,
    WorkManager,
    WorkPlugin,
    WorkResult,
)
from golem.node import GolemNode

logger = logging.getLogger(__name__)


class SequentialWorkManager(ManagerPluginsMixin[WorkPlugin], WorkManager):
    def __init__(self, golem: GolemNode, do_work: DoWorkCallable, *args, **kwargs):
        self._do_work = do_work

        super().__init__(*args, **kwargs)

    def _apply_plugins_from_manager(self, do_work: DoWorkCallable) -> DoWorkCallable:
        logger.debug("Applying plugins from manager...")

        do_work_with_plugins = do_work

        for plugin in self._plugins:
            do_work_with_plugins = plugin(do_work_with_plugins)

        logger.debug("Applying plugins from manager done")

        return do_work_with_plugins

    def _apply_plugins_from_work(self, do_work: DoWorkCallable, work: Work) -> DoWorkCallable:
        logger.debug(f"Applying plugins from `{work}`...")

        work_plugins = getattr(work, WORK_PLUGIN_FIELD_NAME, [])

        if not work_plugins:
            return do_work

        do_work_with_plugins = do_work

        for plugin in work_plugins:
            do_work_with_plugins = plugin(do_work_with_plugins)

        logger.debug(f"Applying plugins from `{work}` done")

        return do_work_with_plugins

    async def do_work(self, work: Work) -> WorkResult:
        logger.debug(f"Running work `{work}`...")

        do_work_with_plugins = self._apply_plugins_from_manager(self._do_work)
        do_work_with_plugins = self._apply_plugins_from_work(do_work_with_plugins, work)

        result = await do_work_with_plugins(work)

        logger.debug(f"Running work `{work}` done")
        logger.info(f"Work `{work}` completed")

        return result

    async def do_work_list(self, work_list: List[Work]) -> List[WorkResult]:
        logger.debug(f"Running work sequence `{work_list}`...")

        results = []

        for i, work in enumerate(work_list):
            logger.debug(f"Doing work sequence #{i}...")

            results.append(await self.do_work(work))

            logger.debug(f"Doing work sequence #{i} done")

        logger.debug(f"Running work sequence `{work_list}` done")

        return results
