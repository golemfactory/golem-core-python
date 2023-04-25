from typing import Union, TYPE_CHECKING
from decimal import Decimal

from ya_payment import RequestorApi, models

from golem_core.core.payment_api.resources.allocation import Allocation

from golem_core.core.resources import Resource, api_call_wrapper, _NULL


if TYPE_CHECKING:
    from golem_core.core.market_api.resources.agreement import Agreement


class Invoice(Resource[RequestorApi, models.Invoice, "Agreement", _NULL, _NULL]):
    """A single invoice on the Golem Network.

    Ususally created by a :any:`GolemNode` initialized with `collect_payment_events = True`."""
    async def accept_full(self, allocation: Allocation) -> None:
        """Accept full invoice amount using a given :any:`Allocation`."""
        amount_str = (await self.get_data()).amount
        await self.accept(allocation, Decimal(amount_str))

    @api_call_wrapper()
    async def accept(self, allocation: Allocation, amount: Union[Decimal, float]) -> None:
        acceptance = models.Acceptance(total_amount_accepted=str(amount), allocation_id=allocation.id)
        await self.api.accept_invoice(self.id, acceptance)

