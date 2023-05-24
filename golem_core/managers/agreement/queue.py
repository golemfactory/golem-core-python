from typing import Callable, Awaitable

from golem_core.core.market_api import Agreement
from golem_core.managers.base import AgreementManager


class QueueAgreementManager(AgreementManager):
    def __init__(self, get_offer: Callable[[], Awaitable['Offer']]):
        self._get_offer = get_offer

    async def get_agreement(self) -> Agreement:
        while True:
            offer = await self._get_offer()

            try:
                agreement = await offer.create_agreement()
                await agreement.confirm()
                await agreement.wait_for_approval()
            except Exception:
                pass
            else:
                return agreement
