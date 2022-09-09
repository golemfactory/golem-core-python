from abc import ABC, abstractmethod
import asyncio
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from golem_api import GolemNode

from .payment import DebitNote, Invoice
from .yagna_event_collector import YagnaEventCollector


class PaymentEventCollector(ABC):
    #   TODO (maybe?):
    #   1. Demand and PoolingBatch should also inherit from this class
    #   2. Merge YagnaEventCollector into it
    _event_collecting_task: Optional[asyncio.Task] = None

    def __init__(self, node: "GolemNode"):
        self.node = node

    def start_collecting_events(self) -> None:
        if self._event_collecting_task is None:
            task = asyncio.get_event_loop().create_task(self._process_yagna_events())
            self._event_collecting_task = task

    async def stop_collecting_events(self) -> None:
        if self._event_collecting_task is not None:
            self._event_collecting_task.cancel()
            await self._event_collecting_task
            self._event_collecting_task = None

    @abstractmethod
    async def _process_yagna_events(self) -> None:
        raise NotImplementedError

    @property
    @abstractmethod
    def api(self):
        raise NotImplementedError


class DebitNoteEventCollector(PaymentEventCollector):
    @property
    def api(self):
        return DebitNote._get_api(self.node)

    async def _process_yagna_events(self) -> None:
        event_collector = YagnaEventCollector(
            self.api.get_debit_note_events,
            [],
            {},
        )
        async with event_collector:
            queue: asyncio.Queue = event_collector.event_queue()
            while True:
                event = await queue.get()
                print("---> GOT EVENT!", event)


class InvoiceEventCollector(PaymentEventCollector):
    @property
    def api(self):
        return Invoice._get_api(self.node)

    async def _process_yagna_events(self) -> None:
        event_collector = YagnaEventCollector(
            self.api.get_invoice_events,
            [],
            {},
        )
        async with event_collector:
            queue: asyncio.Queue = event_collector.event_queue()
            while True:
                event = await queue.get()
                print("---> GOT EVENT!", event)
