import asyncio
from typing import TYPE_CHECKING, Optional, Union

from _decimal import Decimal
from ya_payment import RequestorApi, models

from golem.resources.allocation import Allocation
from golem.resources.base import _NULL, Resource, api_call_wrapper
from golem.resources.debit_note.events import NewDebitNote

if TYPE_CHECKING:
    from golem.node import GolemNode
    from golem.resources.activity import Activity  # noqa


class DebitNote(Resource[RequestorApi, models.DebitNote, "Activity", _NULL, _NULL]):
    """A single debit note on the Golem Network.

    Usually created by a :any:`GolemNode` initialized with `collect_payment_events = True`.
    """

    def __init__(self, node: "GolemNode", id_: str, data: Optional[models.DebitNote] = None):
        super().__init__(node, id_, data)
        asyncio.create_task(node.event_bus.emit(NewDebitNote(self)))

    async def accept_full(self, allocation: Allocation) -> None:
        """Accept full debit note amount using a given :any:`Allocation`."""
        amount_str = (await self.get_data()).total_amount_due
        await self.accept(allocation, Decimal(amount_str))

    @api_call_wrapper()
    async def accept(self, allocation: Allocation, amount: Union[Decimal, float]) -> None:
        acceptance = models.Acceptance(
            total_amount_accepted=str(amount), allocation_id=allocation.id
        )
        await self.api.accept_debit_note(self.id, acceptance)
