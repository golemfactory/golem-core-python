import asyncio
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


class AsynchronousWorkManager(ManagerPluginsMixin[WorkPlugin], WorkManager):
    def __init__(self, golem: GolemNode, do_work: DoWorkCallable, *args, **kwargs):
        self._do_work = do_work

        super().__init__(*args, **kwargs)

    def _apply_plugins_from_manager(self, do_work: DoWorkCallable) -> DoWorkCallable:
        do_work_with_plugins = do_work

        for plugin in self._plugins:
            do_work_with_plugins = plugin(do_work_with_plugins)

        return do_work_with_plugins

    def _apply_plugins_from_work(self, do_work: DoWorkCallable, work: Work) -> DoWorkCallable:
        work_plugins = getattr(work, WORK_PLUGIN_FIELD_NAME, [])

        if not work_plugins:
            return do_work

        do_work_with_plugins = do_work

        for plugin in work_plugins:
            do_work_with_plugins = plugin(do_work_with_plugins)

        return do_work_with_plugins

    async def do_work(self, work: Work) -> WorkResult:
        do_work_with_plugins = self._apply_plugins_from_manager(self._do_work)
        do_work_with_plugins = self._apply_plugins_from_work(do_work_with_plugins, work)

        result = await do_work_with_plugins(work)

        logger.info(f"Work `{work}` completed")

        return result

    async def do_work_list(self, work_list: List[Work]) -> List[WorkResult]:
        results = await asyncio.gather(*[self.do_work(work) for work in work_list])
        return results
