import asyncio
import logging
from typing import Generic, List, Optional, Sequence

from golem.managers.base import ManagerException, TPlugin
from golem.utils.asyncio import create_task_with_logging
from golem.utils.logging import get_trace_id_name, trace_span

logger = logging.getLogger(__name__)


class BackgroundLoopMixin:
    def __init__(self, *args, **kwargs) -> None:
        self._background_loop_task: Optional[asyncio.Task] = None

        super().__init__(*args, **kwargs)

    async def start(self) -> None:
        if self.is_started():
            raise ManagerException("Already started!")

        self._background_loop_task = create_task_with_logging(
            self._background_loop(),
            trace_id=get_trace_id_name(self, "background-loop"),
        )

    async def stop(self) -> None:
        if not self.is_started():
            raise ManagerException("Already stopped!")

        if self._background_loop_task is not None:
            self._background_loop_task.cancel()
            self._background_loop_task = None

    def is_started(self) -> bool:
        return self._background_loop_task is not None and not self._background_loop_task.done()

    async def _background_loop(self) -> None:
        pass


class PluginsMixin(Generic[TPlugin]):
    def __init__(self, plugins: Optional[Sequence[TPlugin]] = None, *args, **kwargs) -> None:
        self._plugins: List[TPlugin] = list(plugins) if plugins is not None else []

        super().__init__(*args, **kwargs)

    @trace_span()
    def register_plugin(self, plugin: TPlugin):
        self._plugins.append(plugin)

    @trace_span()
    def unregister_plugin(self, plugin: TPlugin):
        self._plugins.remove(plugin)
