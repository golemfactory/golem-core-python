from abc import ABC, abstractmethod
import asyncio
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from golem_api import GolemNode


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
            self._event_collecting_task = None

    @abstractmethod
    async def _process_yagna_events(self) -> None:
        raise NotImplementedError


class DebitNoteEventCollector(PaymentEventCollector):
    async def _process_yagna_events(self) -> None:
        await asyncio.sleep(10000)


class InvoiceEventCollector(PaymentEventCollector):
    async def _process_yagna_events(self) -> None:
        await asyncio.sleep(10000)
