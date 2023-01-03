import asyncio

from golem_core.event_bus import EventBus

class ParallelEventBus(EventBus):
    #   EventBus emits event N once callbacks for event N-1 finished.
    #   This event bus emits all events when they come.
    async def _emit_events(self):
        while True:
            event = await self.queue.get()
            asyncio.create_task(self._emit(event))
