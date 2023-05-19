import asyncio
from typing import List

from golem_core.core.golem_node import GolemNode
from golem_core.core.market_api import Proposal
from golem_core.core.resources import ResourceEvent

Offer = Proposal


class StackOfferManager:
    def __init__(self, golem: GolemNode) -> None:
        self._offers: List[Offer] = []
        self._event_bus = golem.event_bus
        self._event_bus.resource_listen(self._on_new_offer, (ResourceEvent,), (Offer,))

    async def _on_new_offer(self, offer_event: ResourceEvent) -> None:
        self._offers.append(offer_event.resource)

    async def get_offer(self) -> Offer:
        # TODO add some timeout
        while True:
            try:
                return self._offers.pop()
            except IndexError:
                # wait for offers
                await asyncio.sleep(1)
                pass
