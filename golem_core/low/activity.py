import asyncio
from typing import Callable, Dict, List, Optional, TYPE_CHECKING, Union
from datetime import timedelta
import json

from ya_activity import models

from golem_core.events import BatchFinished, ResourceClosed
from golem_core.commands import Command
from .payment import DebitNote
from .market import Agreement
from .resource import Resource
from .resource_internals import ActivityApi, _NULL
from .yagna_event_collector import YagnaEventCollector
from .api_call_wrapper import api_call_wrapper
from .exceptions import BatchError, BatchTimeoutError, CommandFailed, CommandCancelled

if TYPE_CHECKING:
    from golem_core import GolemNode


class Activity(Resource[ActivityApi, _NULL, Agreement, "PoolingBatch", _NULL]):
    """A single activity on the Golem Network.

    Either created by :any:`Agreement.create_activity()` or via :any:`GolemNode.activity()`.
    """

    def __init__(self, node: "GolemNode", id_: str):
        super().__init__(node, id_)

        self._running_batch_counter = 0
        self._busy_event = asyncio.Event()
        self._idle_event = asyncio.Event()
        self._idle_event.set()
        self._destroyed_event = asyncio.Event()

    ###################
    #   State management - idle / busy / destroyed
    @property
    def idle(self) -> bool:
        """True if there are no batches being executed now on this :any:`Activity`."""
        return self._idle_event.is_set()

    @property
    def running_batch_counter(self) -> int:
        return self._running_batch_counter

    @running_batch_counter.setter
    def running_batch_counter(self, new_val: int) -> None:
        assert abs(self._running_batch_counter - new_val) == 1  # change by max 1
        assert new_val >= 0
        self._running_batch_counter = new_val
        if new_val == 0:
            self._busy_event.clear()
            self._idle_event.set()
        else:
            self._busy_event.set()
            self._idle_event.clear()

    async def wait_busy(self) -> None:
        """Wait until this :any:`Activity` is no longer :any:`idle`."""
        await self._busy_event.wait()

    async def wait_idle(self) -> None:
        """Wait until this :any:`Activity` is :any:`idle`."""
        await self._idle_event.wait()

    async def wait_destroyed(self) -> None:
        """Wait until this :any:`Activity` is :any:`destroyed`."""
        await self._destroyed_event.wait()

    @property
    def destroyed(self) -> bool:
        """True after a succesful call to :func:`destroy`."""
        return self._destroyed_event.is_set()

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
        """Destroy this :any:`Activity`. This is final, destroyed activities can no longer be used."""
        await self.api.destroy_activity(self.id)
        self._destroyed_event.set()
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
        """Create a new batch that executes given :any:`Command` s in the exe unit.

        Sample usage::

            batch = await activity.execute_commands(
                Deploy(),
                Start(),
                Run("echo -n 'hello world'"),
            )
            await batch.wait()
            print(batch.events[-1].stdout)  # "hello world"
        """

        await asyncio.gather(*[c.before() for c in commands])
        commands_str = json.dumps([c.text() for c in commands])
        batch = await self.execute(models.ExeScriptRequest(text=commands_str))

        async def execute_after() -> None:
            await batch.wait(ignore_errors=True)
            await asyncio.gather(*[c.after() for c in commands])

        asyncio.create_task(execute_after())
        return batch

    async def execute_script(self, script: "Script") -> "PoolingBatch":
        """Create a new batch that executes commands from a given :any:`Script` in the exe unit.

        This is an alternative to :func:`execute_commands` that provides a more granular access to the results.

        Sample usage::

            script = Script()
            script.add_command(Deploy())
            script.add_command(Start())
            result = script.add_command(Run("echo -n 'hello world'"))
            script.add_command(Run("sleep 1000"))

            batch = await activity.execute_script(script)

            #   This line doesn't wait for the whole batch to finish
            print((await result).stdout)  # "hello world"
        """
        batch = await self.execute_commands(*script.commands)
        batch._futures = script.futures
        return batch

    def batch(self, batch_id: str) -> "PoolingBatch":
        """Returns a :any:`PoolingBatch` with a given id (assumed to be correct, there is no validation)."""
        batch = PoolingBatch(self.node, batch_id)
        if batch._parent is None:
            self.add_child(batch)
        return batch

    @property
    def debit_notes(self) -> List[DebitNote]:
        """List of all debit notes for this :any:`Activity`."""
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
    def done(self) -> bool:
        """True if this batch is already finished."""
        return self.finished_event.is_set()

    @property
    def success(self) -> bool:
        """True if this batch finished without errors. Raises `AttributeError` if batch is not :any:`done`."""
        if not self.done:
            raise AttributeError("Success can be determined only for finished batches")
        if not self.events:
            #   We got no events but we're done -> only possibility is event collection failure
            #   (In the future maybe also cancelled batch?)
            return False

        return self.events[-1].result == "Ok"

    async def wait(
        self, timeout: Optional[Union[timedelta, float]] = None, ignore_errors: bool = False,
    ) -> List[models.ExeScriptCommandResult]:
        """Wait until the batch is :any:`done`.

        :param timeout: If not None, :any:`BatchTimeoutError` will be raised if the batch runs longer.
            This exception doesn't stop the execution of the batch.
        :param ignore_errors: When True, :func:`wait` doesn't care if the end of the batch is a :any:`success` or not.
            If False, :any:`BatchError` will be raised for failed batches.
        """
        timeout_seconds: Optional[float]
        if timeout is None:
            timeout_seconds = None
        elif isinstance(timeout, timedelta):
            timeout_seconds = timeout.total_seconds()
        else:
            timeout_seconds = timeout

        try:
            await asyncio.wait_for(self.finished_event.wait(), timeout_seconds)
            if not ignore_errors and not self.success:
                raise BatchError(self)
            return self.events
        except asyncio.TimeoutError:
            assert timeout_seconds is not None  # mypy
            raise BatchTimeoutError(self, timeout_seconds)

    @property
    def events(self) -> List[models.ExeScriptCommandResult]:
        """Returns a list of results for this batch.

        Nth element in the returned list corresponds to the nth command in a batch.

        When the batch is :any:`done`:

        * If the batch is a :any:`success`, there will be a single event for every command.
        * If not, there will be a single event for every succesful command followed by
          an event for the command that failed.

        If the batch is not :any:`done`, events for already finished commands will be returned.
        """
        return super().events

    ###########################
    #   Event collector methods
    async def _collect_yagna_events(self) -> None:
        try:
            await super()._collect_yagna_events()
        except Exception:
            #   This happens when activity is destroyed when we're waiting for batch results
            #   (I'm not sure if always - for sure when provider destroys activity because
            #   agreement timed out). Maybe some other scenarios are also possible.
            self._set_finished()

    def _collect_events_kwargs(self) -> Dict:
        return {"timeout": 5, "_request_timeout": 5.5}

    def _collect_events_args(self) -> List:
        return [self.parent.id, self.id]

    @property
    def _collect_events_func(self) -> Callable:
        return self.api.get_exec_batch_results

    async def _process_event(self, event: models.ExeScriptCommandResult) -> None:
        if event.index < len(self.events):
            #   Repeated event
            return

        self.add_event(event)

        if self._futures is not None:
            if event.result == 'Error':
                self._futures[event.index].set_exception(CommandFailed(self))
                for fut in self._futures[event.index + 1:]:
                    fut.set_exception(CommandCancelled(self))
            else:
                self._futures[event.index].set_result(event)

        if event.is_batch_finished:
            self._set_finished()

    def _set_finished(self) -> None:
        self.node.event_bus.emit(BatchFinished(self))
        self.finished_event.set()
        self.parent.running_batch_counter -= 1
        self.stop_collecting_events()


class Script:
    """A helper class for executing multiple commands in a single batch. Details: :any:`execute_script`."""
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
        """Add a :any:`Command` to the script.

        Returns an awaitable that will (after a call to :any:`execute_script`):

        * Return the result of the command once it finished succesfully
        * Raise :any:`CommandFailed` if the command failed
        * Raise :any:`CommandCancelled` if any previous command in the same batch failed

        """
        self._commands.append(command)
        fut: asyncio.Future[models.ExeScriptCommandResult] = asyncio.Future()
        self._futures.append(fut)
        return fut
