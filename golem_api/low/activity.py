import asyncio
from typing import Callable, Dict, List, Optional, TYPE_CHECKING
from datetime import timedelta
import json

from ya_activity import models

from golem_api.events import ResourceClosed
from golem_api.commands import Command
from .payment import DebitNote
from .market import Agreement
from .resource import Resource
from .resource_internals import ActivityApi, _NULL
from .yagna_event_collector import YagnaEventCollector
from .api_call_wrapper import api_call_wrapper

if TYPE_CHECKING:
    from golem_api import GolemNode


class Activity(Resource[ActivityApi, _NULL, Agreement, "PoolingBatch", _NULL]):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._running_batch_counter = 0

        self.busy_event = asyncio.Event()
        self.idle_event = asyncio.Event()
        self.idle = True

        #   TODO: state management is just a draft now, but it's far from obvious how
        #         it should be implemented (--> maybe this draft is enough?)
        self._terminated: Optional[bool] = None

    ###################
    #   State management - terminated / idle / busy
    @property
    def terminated(self) -> bool:
        if self._terminated is None:
            #   This is a case where we didn't create a new activity, but got an activity via
            #   GolemNode.activity(activity_id), for activity created in some other way.
            #   We don't need this now.
            raise NotImplementedError("State of activity is supported only for newly created activities")
        return self._terminated

    @property
    def idle(self) -> bool:
        return self.idle_event.is_set()

    @idle.setter
    def idle(self, val: bool) -> None:
        if val:
            self.busy_event.clear()
            self.idle_event.set()
        else:
            self.busy_event.set()
            self.idle_event.clear()

    @property
    def running_batch_counter(self) -> int:
        return self._running_batch_counter

    @running_batch_counter.setter
    def running_batch_counter(self, new_val) -> None:
        assert abs(self._running_batch_counter - new_val) == 1  # change by max 1
        assert new_val >= 0
        self._running_batch_counter = new_val
        if new_val == 0:
            self.idle = True
        elif self.idle:
            self.idle = False

    ####################
    #   API
    @classmethod
    async def create(cls, node: "GolemNode", agreement_id: str, timeout: timedelta) -> "Activity":
        api = cls._get_api(node)
        activity_id = await api.create_activity(agreement_id, timeout=timeout.total_seconds())
        activity = cls(node, activity_id)
        activity._terminated = False
        return activity

    @api_call_wrapper()
    async def destroy(self) -> None:
        self._terminated = True
        await self.api.destroy_activity(self.id)
        self.node.event_bus.emit(ResourceClosed(self))

    @api_call_wrapper()
    async def execute(self, script: models.ExeScriptRequest) -> "PoolingBatch":
        batch_id = await self.api.call_exec(self.id, script)
        batch = PoolingBatch(self.node, batch_id)
        batch.start_collecting_events()
        self.add_child(batch)
        self.running_batch_counter += 1
        return batch

    async def execute_commands(self, *commands: Command) -> "PoolingBatch":
        commands_str = json.dumps([c.text() for c in commands])
        return await self.execute(models.ExeScriptRequest(text=commands_str))

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

        batch = activity.execute_commands(Deploy(), Start())
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
    def _collect_events_kwargs(self) -> Dict:
        return {"timeout": 5, "_request_timeout": 5.5}

    def _collect_events_args(self) -> List:
        return [self.activity.id, self.id]

    @property
    def _collect_events_func(self) -> Callable:
        return self.api.get_exec_batch_results  # type: ignore

    async def _process_event(self, event: models.ExeScriptCommandResult) -> None:
        if event.index < len(self.events):
            #   Repeated event
            return
        self.add_event(event)
        if event.is_batch_finished:
            self._finished.set_result(None)
            self.parent.running_batch_counter -= 1
            await self.stop_collecting_events()
