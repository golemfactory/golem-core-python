from typing import Awaitable, Callable

from golem_core.core.market_api import Agreement
from golem_core.managers.base import AgreementManager


class SingleUseAgreementManager(AgreementManager):
    def __init__(self, get_offer: Callable[[], Awaitable["Offer"]], event_bus):
        self._get_offer = get_offer
        self._event_bus = event_bus

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
                self._event_bus.register(
                    AgreementReleased(agreement=agreement), self._on_agreement_released
                )
                return agreement

    async def _on_agreement_released(self, event) -> None:
        agreement = event.agreement
        await agreement.terminate()
