import asyncio
from datetime import datetime

from golem_core.core.golem_node.golem_node import GolemNode
from golem_core.core.market_api import RepositoryVmPayload
from golem_core.managers.negotiation import AlfaNegotiationManager
from golem_core.managers.offer import StackOfferManager


def get_allocation_factory(golem: GolemNode):
    async def _get_allocation():
        return await golem.create_allocation(1)

    return _get_allocation


async def main():
    payload = RepositoryVmPayload("9a3b5d67b0b27746283cb5f287c13eab1beaa12d92a9f536b747c7ae")
    async with GolemNode() as golem:
        offer_manager = StackOfferManager(golem)
        negotiation_manager = AlfaNegotiationManager(golem, get_allocation_factory(golem))
        await negotiation_manager.start_negotiation(payload)

        for i in range(1, 16):
            print(f"Got offer {i}: {(await offer_manager.get_offer()).id}...")
            print(f"{datetime.utcnow()} sleeping...")
            await asyncio.sleep(1)
        print(f"{datetime.utcnow()} stopping negotiations...")
        await negotiation_manager.stop_negotiation()


if __name__ == "__main__":
    asyncio.run(main())
