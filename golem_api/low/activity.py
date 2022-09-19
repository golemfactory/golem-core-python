import asyncio
from typing import Callable, Dict, List, Optional, TYPE_CHECKING, Union
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
from .exceptions import BatchTimeoutError

if TYPE_CHECKING:
    from golem_api import GolemNode


class Activity(Resource[ActivityApi, _NULL, Agreement, "PoolingBatch", _NULL]):
    def __init__(self, node: "GolemNode", id_: str):
        super().__init__(node, id_)
        self._running_batch_counter = 0

        self.busy_event = asyncio.Event()
        self.idle_event = asyncio.Event()
        self.destroyed_event = asyncio.Event()
        self.idle = True

    ###################
    #   State management - idle / busy
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
    def running_batch_counter(self, new_val: int) -> None:
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
        return activity

    @api_call_wrapper()
    async def destroy(self) -> None:
        self.destroyed_event.set()
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

    async def execute_script(self, script: "Script") -> "PoolingBatch":
        batch = await self.execute_commands(*script.commands)
        batch._futures = script.futures
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

        batch = activity.execute_commands(Deploy(), Start())
        await batch.wait()
        for event in batch.events:
            print(event.stdout)
    """
    _event_collecting_task: Optional[asyncio.Task] = None

    def __init__(self, node: "GolemNode", id_: str):
        super().__init__(node, id_)

        self.finished_event = asyncio.Event()
        self._futures: Optional[List[asyncio.Future[models.ExeScriptCommandResult]]] = None

    @property
    def activity(self) -> "Activity":
        return self.parent

    @property
    def done(self) -> bool:
        return self.finished_event.is_set()

    async def wait(self, timeout: Optional[Union[timedelta, float]] = None) -> List[models.ExeScriptCommandResult]:
        #   NOTE: timeout doesn't stop the batch, just raises an exception
        timeout_seconds: Optional[float]
        if timeout is None:
            timeout_seconds = None
        elif isinstance(timeout, timedelta):
            timeout_seconds = timeout.total_seconds()
        else:
            timeout_seconds = timeout

        try:
            await asyncio.wait_for(self.finished_event.wait(), timeout_seconds)
            return self.events
        except asyncio.TimeoutError:
            assert timeout_seconds is not None  # mypy
            raise BatchTimeoutError(self, timeout_seconds)

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

        if self._futures is not None:
            fut = self._futures[event.index]
            assert not fut.done()
            fut.set_result(event)

        if event.is_batch_finished:
            self.finished_event.set()
            self.parent.running_batch_counter -= 1
            await self.stop_collecting_events()


class Script:
    def __init__(self) -> None:
        self._commands: List[Command] = []
        self._futures: List[asyncio.Future[models.ExeScriptCommandResult]] = []

    @property
    def commands(self) -> List[Command]:
        return self._commands.copy()

    @property
    def futures(self) -> "List[asyncio.Future[models.ExeScriptCommandResult]]":
        return self._futures.copy()

    def add_command(self, command: Command) -> "asyncio.Future[models.ExeScriptCommandResult]":
        self._commands.append(command)
        fut: asyncio.Future[models.ExeScriptCommandResult] = asyncio.Future()
        self._futures.append(fut)
        return fut
