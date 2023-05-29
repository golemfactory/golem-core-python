import asyncio
import logging
from typing import List

from golem_core.core.market_api import Proposal

logger = logging.getLogger(__name__)
Offer = Proposal


class StackOfferManager:
    def __init__(self, get_offer) -> None:
        self._get_offer = get_offer
        self._offers: asyncio.Queue[Proposal] = asyncio.Queue()
        self._tasks: List[asyncio.Task] = []

    async def start_consuming_offers(self) -> None:
        logger.debug("Starting manager")
        self._tasks.append(asyncio.create_task(self._consume_offers()))

    async def stop_consuming_offers(self) -> None:
        for task in self._tasks:
            logger.debug("Stopping manager")
            task.cancel()

    async def _consume_offers(self) -> None:
        while True:
            offer = await self._get_offer()
            logger.debug("Adding offer to the stack")
            await self._offers.put(offer)

    async def get_offer(self) -> Offer:
        offer = await self._offers.get()
        logger.debug("Returning offer from the stack")
        return offer
