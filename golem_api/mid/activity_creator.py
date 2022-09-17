from typing import Optional
from golem_api.low.market import Agreement
from golem_api.low.activity import Activity

from .buffered_pipe import BufferedPipe


class ActivityCreator(BufferedPipe[Agreement, Activity]):
    async def _process_single_item(self, agreement: Agreement) -> Optional[Activity]:
        try:
            return await agreement.create_activity()
        except Exception as e:
            print(e)
            return None
