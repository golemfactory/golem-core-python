import asyncio
from datetime import datetime

from golem_core.core.golem_node.golem_node import GolemNode
from golem_core.core.market_api import RepositoryVmPayload
from golem_core.managers.negotiation import AlfaNegotiationManager
from golem_core.managers.offer import StackOfferManager
from golem_core.managers.payment.pay_all import PayAllPaymentManager


async def main():
    payload = RepositoryVmPayload("9a3b5d67b0b27746283cb5f287c13eab1beaa12d92a9f536b747c7ae")
    async with GolemNode() as golem:
        payment_manager = PayAllPaymentManager(golem, budget=1.0)
        negotiation_manager = AlfaNegotiationManager(golem, payment_manager.get_allocation)
        offer_manager = StackOfferManager(negotiation_manager.get_offer)
        await negotiation_manager.start_negotiation(payload)
        await offer_manager.start_consuming_offers()

        for i in range(10):
            print(f"Got offer {i}: {(await offer_manager.get_offer()).id}...")
            print(f"{datetime.utcnow()} sleeping...")
            await asyncio.sleep(1)

        print(f"{datetime.utcnow()} stopping negotiations...")
        await offer_manager.stop_consuming_offers()
        await negotiation_manager.stop_negotiation()


if __name__ == "__main__":
    asyncio.run(main())
