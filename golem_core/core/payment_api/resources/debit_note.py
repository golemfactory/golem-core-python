from typing import Union, TYPE_CHECKING

from _decimal import Decimal

from ya_payment import RequestorApi, models

from golem_core.core.resources import Resource, api_call_wrapper, _NULL
from golem_core.core.payment_api.resources.allocation import Allocation


if TYPE_CHECKING:
    from golem_core.core.activity_api import Activity


class DebitNote(Resource[RequestorApi, models.DebitNote, "Activity", _NULL, _NULL]):
    """A single debit note on the Golem Network.

    Ususally created by a :any:`GolemNode` initialized with `collect_payment_events = True`.
    """
    async def accept_full(self, allocation: Allocation) -> None:
        """Accept full debit note amount using a given :any:`Allocation`."""
        amount_str = (await self.get_data()).total_amount_due
        await self.accept(allocation, Decimal(amount_str))

    @api_call_wrapper()
    async def accept(self, allocation: Allocation, amount: Union[Decimal, float]) -> None:
        acceptance = models.Acceptance(total_amount_accepted=str(amount), allocation_id=allocation.id)
        await self.api.accept_debit_note(self.id, acceptance)
