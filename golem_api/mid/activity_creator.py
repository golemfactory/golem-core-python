from typing import Optional

from golem_api.low.market import Agreement
from golem_api.low.activity import Activity
from .map import Map


async def create_activity(agreement: Agreement) -> Optional[Activity]:
    try:
        return await agreement.create_activity()
    except Exception as e:
        print(e)
        return None


class ActivityCreator(Map[Agreement, Activity]):
    def __init__(self) -> None:
        return super().__init__(create_activity, True)
