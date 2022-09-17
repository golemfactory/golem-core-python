from golem_api.low.market import Agreement
from golem_api.low.activity import Activity
from .map import Map


async def create_activity(agreement: Agreement) -> Activity:
    return await agreement.create_activity()


class ActivityCreator(Map[Agreement, Activity]):
    def __init__(self) -> None:
        return super().__init__(create_activity, True)
