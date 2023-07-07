import logging

from golem.managers.base import (
    WORK_PLUGIN_FIELD_NAME,
    DoWorkCallable,
    ManagerPluginsMixin,
    Work,
    WorkManagerPlugin,
    WorkResult,
)

logger = logging.getLogger(__name__)


class WorkManagerPluginsMixin(ManagerPluginsMixin[WorkManagerPlugin]):
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

    async def _do_work_with_plugins(self, do_work: DoWorkCallable, work: Work) -> WorkResult:
        do_work_with_plugins = self._apply_plugins_from_manager(do_work)
        do_work_with_plugins = self._apply_plugins_from_work(do_work_with_plugins, work)
        return await do_work_with_plugins(work)
