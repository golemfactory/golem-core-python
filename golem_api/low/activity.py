import asyncio
from typing import List, Optional, TYPE_CHECKING
from datetime import timedelta
import json

from ya_activity import models

from golem_api.events import ResourceClosed
from .payment import DebitNote
from .market import Agreement
from .resource import Resource
from .resource_internals import ActivityApi, _NULL
from .yagna_event_collector import YagnaEventCollector

if TYPE_CHECKING:
    from golem_api import GolemNode


class Activity(Resource[ActivityApi, _NULL, Agreement, "PoolingBatch", _NULL]):
    @classmethod
    async def create(cls, node: "GolemNode", agreement_id: str, timeout: timedelta) -> "Activity":
        api = cls._get_api(node)
        activity_id = await api.create_activity(agreement_id, timeout=timeout.total_seconds())
        return cls(node, activity_id)

    async def destroy(self) -> None:
        await self.api.destroy_activity(self.id)
        self.node.event_bus.emit(ResourceClosed(self))

    async def raw_exec(self, commands: List[dict], autostart: bool = True) -> "PoolingBatch":
        commands_str = json.dumps(commands)
        batch_id = await self.api.call_exec(self.id, models.ExeScriptRequest(text=commands_str))
        batch = PoolingBatch(self.node, batch_id)
        self.add_child(batch)

        if autostart:
            batch.start_collecting_events()

        return batch

    def batch(self, batch_id: str) -> "PoolingBatch":
        batch = PoolingBatch(self.node, batch_id)
        if batch._parent is None:
            self.add_child(batch)
        return batch

    @property
    def debit_notes(self) -> List[DebitNote]:
        return [child for child in self.children if isinstance(child, DebitNote)]


class PoolingBatch(
    Resource[ActivityApi, _NULL, Activity, _NULL, models.ExeScriptCommandResult],
    YagnaEventCollector
):
    """A single batch of commands.

    Usage::

        batch = activity.raw_exec([{"deploy": {}}, {"start": {}}])
        await batch.finished
        for event in batch.events:
            print(event.stdout)
    """
    _event_collecting_task: Optional[asyncio.Task] = None

    def __init__(self, node: "GolemNode", id_: str):
        super().__init__(node, id_)

        self._finished: asyncio.Future = asyncio.Future()

    @property
    def activity(self) -> "Activity":
        return self.parent

    @property
    async def finished(self) -> None:
        await self._finished

    ###########################
    #   Event collector methods
    def _collect_events_kwargs(self):
        return {"timeout": 5, "_request_timeout": 5.5}

    def _collect_events_args(self):
        return [self.activity.id, self.id]

    @property
    def _collect_events_func(self):
        return self.api.get_exec_batch_results

    async def _process_event(self, event):
        if event.index < len(self.events):
            #   Repeated event
            return
        self.add_event(event)
        if event.is_batch_finished:
            self._finished.set_result(None)
            await self.stop_collecting_events()
