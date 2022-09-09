from typing import AsyncIterator, Optional
from golem_api.low.market import Agreement
from golem_api.low.activity import Activity


class ActivityCreator:
    async def __call__(self, agreements: AsyncIterator[Agreement]) -> AsyncIterator[Activity]:
        async for agreement in agreements:
            activity = await self._create_activity(agreement)
            if activity is not None:
                yield activity

    async def _create_activity(self, agreement: Agreement) -> Optional[Activity]:
        try:
            return await agreement.create_activity()
        except Exception as e:
            print(e)
            return None
