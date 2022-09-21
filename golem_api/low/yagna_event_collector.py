from abc import ABC, abstractmethod
import asyncio
#   TODO: replace Any here
from typing import Any, Callable, Dict, List, Optional


class YagnaEventCollector(ABC):
    _event_collecting_task: Optional[asyncio.Task] = None

    def start_collecting_events(self) -> None:
        if self._event_collecting_task is None:
            task = asyncio.get_event_loop().create_task(self._collect_yagna_events())
            self._event_collecting_task = task

    def stop_collecting_events(self) -> None:
        if self._event_collecting_task is not None:
            self._event_collecting_task.cancel()
            self._event_collecting_task = None

    async def _collect_yagna_events(self) -> None:
        while True:
            args = self._collect_events_args()
            kwargs = self._collect_events_kwargs()
            events = await self._collect_events_func(*args, **kwargs)
            if events:
                for event in events:
                    await self._process_event(event)

    @property
    @abstractmethod
    def _collect_events_func(self) -> Callable:
        raise NotImplementedError

    @abstractmethod
    async def _process_event(self, event: Any) -> None:
        raise NotImplementedError

    def _collect_events_args(self) -> List:
        return []

    def _collect_events_kwargs(self) -> Dict:
        return {}
