import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Union

from ya_activity import models

from golem.resources.base import _NULL, Resource
from golem.resources.pooling_batch.events import BatchFinished, NewPoolingBatch
from golem.resources.pooling_batch.exceptions import (
    BatchError,
    BatchTimeoutError,
    CommandCancelled,
    CommandFailed,
)
from golem.utils.low import ActivityApi, YagnaEventCollector

if TYPE_CHECKING:
    from golem.node import GolemNode
    from golem.resources.activity.activity import Activity  # noqa


class PoolingBatch(
    Resource[ActivityApi, _NULL, "Activity", _NULL, models.ExeScriptCommandResult],
    YagnaEventCollector,
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
        asyncio.create_task(node.event_bus.emit(NewPoolingBatch(self)))

        self.finished_event = asyncio.Event()
        self._futures: Optional[List[asyncio.Future[models.ExeScriptCommandResult]]] = None

    @property
    def done(self) -> bool:
        """True if this batch is already finished."""
        return self.finished_event.is_set()

    @property
    def success(self) -> bool:
        """True if this batch finished without errors. Raises `AttributeError` if batch is not \
        :any:`done`."""
        if not self.done:
            raise AttributeError("Success can be determined only for finished batches")
        if not self.events:
            #   We got no events but we're done -> only possibility is event collection failure
            #   (In the future maybe also cancelled batch?)
            return False

        return self.events[-1].result == "Ok"

    async def wait(
        self,
        timeout: Optional[Union[timedelta, float]] = None,
        ignore_errors: bool = False,
    ) -> List[models.ExeScriptCommandResult]:
        """Wait until the batch is :any:`done`.

        :param timeout: If not None, :any:`BatchTimeoutError` will be raised if the batch runs
            longer. This exception doesn't stop the execution of the batch.
        :param ignore_errors: When True, :func:`wait` doesn't care if the end of the batch is a
            :any:`success` or not. If False, :any:`BatchError` will be raised for failed batches.
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
        * If not, there will be a single event for every successful command followed by
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
            await self._set_finished()

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
            if event.result == "Error":
                self._futures[event.index].set_exception(CommandFailed(self))
                for fut in self._futures[event.index + 1 :]:
                    fut.set_exception(CommandCancelled(self))
            else:
                self._futures[event.index].set_result(event)

        if event.is_batch_finished:
            await self._set_finished()

    async def _set_finished(self) -> None:
        await self.node.event_bus.emit(BatchFinished(self))
        self.finished_event.set()
        self.parent.running_batch_counter -= 1
        self.stop_collecting_events()
