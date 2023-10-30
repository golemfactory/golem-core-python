import asyncio
from decimal import Decimal
from typing import TYPE_CHECKING, Optional, Union

from ya_payment import RequestorApi, models

from golem.resources.allocation.allocation import Allocation
from golem.resources.base import _NULL, Resource, api_call_wrapper
from golem.resources.invoice.events import NewInvoice

if TYPE_CHECKING:
    from golem.node import GolemNode
    from golem.resources.agreement import Agreement  # noqa


class Invoice(Resource[RequestorApi, models.Invoice, "Agreement", _NULL, _NULL]):
    """A single invoice on the Golem Network.

    Usually created by a :any:`GolemNode` initialized with `collect_payment_events = True`.
    """

    def __init__(self, node: "GolemNode", id_: str, data: Optional[models.Invoice] = None):
        super().__init__(node, id_, data)
        asyncio.create_task(node.event_bus.emit(NewInvoice(self)))

    async def accept_full(self, allocation: Allocation) -> None:
        """Accept full invoice amount using a given :any:`Allocation`."""
        amount_str = (await self.get_data()).amount
        await self.accept(allocation, Decimal(amount_str))

    @api_call_wrapper()
    async def accept(self, allocation: Allocation, amount: Union[Decimal, float]) -> None:
        acceptance = models.Acceptance(
            total_amount_accepted=str(amount), allocation_id=allocation.id
        )
        await self.api.accept_invoice(self.id, acceptance)
