import asyncio
import json
from datetime import timedelta
from typing import TYPE_CHECKING, List

from ya_activity import models

from golem.resources.activity.commands import Command, Script
from golem.resources.activity.events import ActivityClosed, NewActivity
from golem.resources.base import _NULL, Resource, api_call_wrapper
from golem.resources.debit_note import DebitNote
from golem.resources.pooling_batch import PoolingBatch
from golem.utils.low import ActivityApi

if TYPE_CHECKING:
    from golem.node import GolemNode
    from golem.resources.agreement import Agreement  # noqa


class Activity(Resource[ActivityApi, _NULL, "Agreement", PoolingBatch, _NULL]):
    """A single activity on the Golem Network.

    Either created by :any:`Agreement.create_activity()` or via :any:`GolemNode.activity()`.
    """

    def __init__(self, node: "GolemNode", id_: str):
        super().__init__(node, id_)

        asyncio.create_task(node.event_bus.emit(NewActivity(self)))

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
        """True after a successful call to :func:`destroy`."""
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
        """Destroy this :any:`Activity`. This is final, destroyed activities can no longer be \
        used."""
        await self.api.destroy_activity(self.id)
        self._destroyed_event.set()
        await self.node.event_bus.emit(ActivityClosed(self))

    @api_call_wrapper()
    async def execute(self, script: models.ExeScriptRequest) -> PoolingBatch:
        batch_id = await self.api.call_exec(self.id, script)
        batch = PoolingBatch(self.node, batch_id)
        batch.start_collecting_events()
        self.add_child(batch)
        self.running_batch_counter += 1
        return batch

    async def execute_commands(self, *commands: Command) -> PoolingBatch:
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

    async def execute_script(self, script: "Script") -> PoolingBatch:
        """Create a new batch that executes commands from a given :any:`Script` in the exe unit.

        This is an alternative to :func:`execute_commands` that provides a more granular access to
        the results.

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

    def batch(self, batch_id: str) -> PoolingBatch:
        """Return a :any:`PoolingBatch` with a given id.

        Id is assume to be correct, there is no validation.
        """
        batch = PoolingBatch(self.node, batch_id)
        if batch._parent is None:
            self.add_child(batch)
        return batch

    @property
    def debit_notes(self) -> List[DebitNote]:
        """List of all debit notes for this :any:`Activity`."""
        return [child for child in self.children if isinstance(child, DebitNote)]

    @property
    def agreement(self) -> "Agreement":
        return self.parent
