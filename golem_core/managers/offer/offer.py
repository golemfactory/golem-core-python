import asyncio
from typing import List

from golem_core.core.market_api import Proposal

Offer = Proposal


class StackOfferManager:
    def __init__(self, get_offer) -> None:
        self._get_offer = get_offer
        self._offers: List[Offer] = []
        self._tasks: List[asyncio.Task] = []

    async def start_consuming_offers(self) -> None:
        self._tasks.append(asyncio.create_task(self._consume_offers()))

    async def stop_consuming_offers(self) -> None:
        for task in self._tasks:
            task.cancel()

    async def _consume_offers(self) -> None:
        while True:
            self._offers.append(await self._get_offer())
            await asyncio.sleep(1)

    async def get_offer(self) -> Offer:
        # TODO add some timeout
        while True:
            try:
                return self._offers.pop()
            except IndexError:
                # wait for offers
                await asyncio.sleep(1)
