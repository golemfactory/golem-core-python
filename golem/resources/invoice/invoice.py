import asyncio
import logging
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Optional, Tuple, Union

from ya_payment import RequestorApi, models

from golem.resources.allocation.allocation import Allocation
from golem.resources.base import _NULL, Resource, api_call_wrapper
from golem.resources.exceptions import PaymentValidationException
from golem.resources.invoice.events import NewInvoice
from golem.resources.utils.infrastructure import InfrastructureProps
from golem.resources.utils.payment import (
    LinearCoeffs,
    PayDocumentStatus,
    eth_decimal,
    validate_payment_max_cost,
)

if TYPE_CHECKING:
    from golem.node import GolemNode
    from golem.resources.agreement import Agreement  # noqa
    from golem.resources.agreement.data import AgreementData  # noqa

logger = logging.getLogger(__name__)


class Invoice(Resource[RequestorApi, models.Invoice, "Agreement", _NULL, _NULL]):
    """A single invoice on the Golem Network.

    Usually created by a :any:`GolemNode` initialized with `collect_payment_events = True`.
    """

    @property
    def agreement(self) -> "Agreement":
        return self.parent

    def __init__(self, node: "GolemNode", id_: str, data: Optional[models.Invoice] = None):
        super().__init__(node, id_, data)
        asyncio.create_task(node.event_bus.emit(NewInvoice(self)))

    async def get_time_and_amount_since_latest_debit_notes(
        self, total_amount: Decimal
    ) -> Tuple[Optional[timedelta], Decimal]:
        """Get cumulative time and amount since last debit notes from all activities."""
        cumulative_time_from_all_activities = timedelta()
        cumulative_amount_from_all_activities = Decimal(0)

        for activity in self.agreement.activities:
            # Look for a newest Debit Note that came before the invoice
            for debit_note in sorted(
                activity.debit_notes, key=lambda dn: dn.created_at, reverse=True
            ):
                await debit_note.get_data()  # ensure there is access to `debit_note.data``
                if debit_note.created_at < self.created_at:
                    cumulative_time_from_all_activities += self.created_at - debit_note.created_at
                    cumulative_amount_from_all_activities += eth_decimal(
                        debit_note.data.total_amount_due
                    )
                break

        if cumulative_time_from_all_activities == timedelta():
            cumulative_time_from_all_activities = None  # type: ignore[assignment]

        return (
            cumulative_time_from_all_activities,
            total_amount - cumulative_amount_from_all_activities,
        )

    async def validate_and_accept(self, allocation: Allocation) -> None:
        """Validate invoice and accept using a given :any:`Allocation`."""
        invoice_data = await self.get_data(force=True)
        if invoice_data.status != PayDocumentStatus.RECEIVED:
            logger.warning(f"Wrong status of invoice {invoice_data.status} != RECEIVED")
            return

        agreement_data: "AgreementData" = await self.agreement.get_agreement_data(force=True)
        if agreement_data.agreement_duration is None:
            logger.warning("Agreement was not approved")
            return

        try:
            amount_due = eth_decimal(invoice_data.amount)
            (
                cumulative_time_since_last_dn,
                cumulative_amount_since_last_dn,
            ) = await self.get_time_and_amount_since_latest_debit_notes(amount_due)
            coeffs = LinearCoeffs.from_properties(agreement_data.properties)
            infrastructure = InfrastructureProps.from_properties(agreement_data.properties)

            max_cost, max_cost_since_latest_debit_notes = validate_payment_max_cost(
                coeffs=coeffs,
                inf=infrastructure,
                duration=agreement_data.agreement_duration,
                amount=amount_due,
                time_since_last_debit_note=cumulative_time_since_last_dn,
                amount_since_last_debit_note=cumulative_amount_since_last_dn,
            )
        except PaymentValidationException:
            logger.warning(
                f"Invoice {self.id} validation failed. {coeffs=}, {infrastructure=}, "
                f"{agreement_data.agreement_duration=}, {amount_due=}, "
                f"{cumulative_time_since_last_dn=}, {cumulative_amount_since_last_dn=}",
                exc_info=True,
            )
            return

        logger.info(
            f"Accepting Invoice for {self.agreement.id=} "
            f"{amount_due=} {max_cost=} {max_cost_since_latest_debit_notes=}"
        )
        await self.accept(allocation, amount_due)

    async def accept_full(self, allocation: Allocation) -> None:
        """Accept full invoice amount using a given :any:`Allocation`."""
        amount_str = (await self.get_data()).amount
        await self.accept(allocation, Decimal(amount_str))

    @api_call_wrapper(retry_count=5)
    async def accept(self, allocation: Allocation, amount: Union[Decimal, float]) -> None:
        acceptance = models.Acceptance(
            total_amount_accepted=str(amount), allocation_id=allocation.id
        )
        await self.api.accept_invoice(self.id, acceptance)
