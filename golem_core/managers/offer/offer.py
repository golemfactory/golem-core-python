import asyncio
from typing import List

from golem_core.core.market_api import Proposal

Offer = Proposal


class StackOfferManager:
    def __init__(self, get_offer) -> None:
        self._get_offer = get_offer
        self._offers: asyncio.Queue[Proposal] = asyncio.Queue()
        self._tasks: List[asyncio.Task] = []

    async def start_consuming_offers(self) -> None:
        self._tasks.append(asyncio.create_task(self._consume_offers()))

    async def stop_consuming_offers(self) -> None:
        for task in self._tasks:
            task.cancel()

    async def _consume_offers(self) -> None:
        while True:
            await self._offers.put(await self._get_offer())

    async def get_offer(self) -> Offer:
        return await self._offers.get()
