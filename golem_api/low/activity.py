import asyncio
from typing import List, Optional, TYPE_CHECKING
from datetime import timedelta
import json

from ya_activity import models

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

    async def raw_exec(self, commands: List[dict], autostart: bool = True) -> "PoolingBatch":
        commands_str = json.dumps(commands)
        batch_id = await self.api.call_exec(self.id, models.ExeScriptRequest(text=commands_str))
        batch = PoolingBatch(self.node, batch_id)
        self.add_child(batch)

        if autostart:
            batch.start_collecting_events()

        return batch

    def batch(self, batch_id) -> "PoolingBatch":
        batch = PoolingBatch(self.node, batch_id)
        if batch._parent is None:
            self.add_child(batch)
        return batch


class PoolingBatch(Resource[ActivityApi, _NULL, Activity, _NULL, models.ExeScriptCommandResult]):
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
    async def finished(self):
        await self._finished

    def start_collecting_events(self):
        if self._event_collecting_task is None:
            task = asyncio.get_event_loop().create_task(self._process_yagna_events())
            self._event_collecting_task = task

    async def stop_collecting_events(self) -> None:
        """Stop collecting events, after a prior call to :func:`start_collecting_events`."""
        if self._event_collecting_task is not None:
            self._event_collecting_task.cancel()
            self._event_collecting_task = None

    async def _process_yagna_events(self) -> None:
        event_collector = YagnaEventCollector(
            self.api.get_exec_batch_results,
            [self.activity.id, self.id],
            {"timeout": 5, "_request_timeout": 5.5},
        )
        async with event_collector:
            queue: asyncio.Queue = event_collector.event_queue()
            while True:
                event = await queue.get()
                if event.index < len(self.events):
                    #   YagnaEventCollector assumes events don't repeat
                    #   (this is true e.g. for Demand events), but they do repeat -
                    #   each time YagnaEventCollector asks for batch events it gets all
                    #   already finished events.
                    #
                    #   (this is not very pretty, but quite harmless -> possible TODO
                    #   for YagnaEventCollector).
                    continue
                self.add_event(event)
                if event.is_batch_finished:
                    self._finished.set_result(None)
                    break
