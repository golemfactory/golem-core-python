import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Optional, Union

from ya_payment import RequestorApi, models

from golem.resources.allocation import Allocation
from golem.resources.base import _NULL, Resource, api_call_wrapper
from golem.resources.debit_note.events import NewDebitNote
from golem.resources.exceptions import PaymentValidationException
from golem.resources.utils.infrastructure import InfrastructureProps
from golem.resources.utils.payment import (
    LinearCoeffs,
    PayDocumentStatus,
    PaymentProps,
    eth_decimal,
    validate_payment_calculated_cost,
    validate_payment_max_cost,
)

if TYPE_CHECKING:
    from golem.node import GolemNode
    from golem.resources.activity import Activity  # noqa
    from golem.resources.agreement.data import AgreementData  # noqa

logger = logging.getLogger(__name__)


class DebitNote(Resource[RequestorApi, models.DebitNote, "Activity", _NULL, _NULL]):
    """A single debit note on the Golem Network.

    Usually created by a :any:`GolemNode` initialized with `collect_payment_events = True`.
    """

    def __init__(self, node: "GolemNode", id_: str, data: Optional[models.DebitNote] = None):
        super().__init__(node, id_, data)
        asyncio.create_task(node.event_bus.emit(NewDebitNote(self)))

    @property
    def activity(self) -> "Activity":
        return self.parent

    async def get_status(self) -> PayDocumentStatus:
        return PayDocumentStatus(str((await self.get_data()).status).upper())

    async def get_previous_debit_note_data(self, timestamp: datetime) -> Optional[models.DebitNote]:
        """Get latest debit note data from before given `timestamp`."""
        debit_notes_data = [(await dn.get_data()) for dn in self.parent.debit_notes]
        debit_notes_data.sort(key=lambda dn: dn.timestamp, reverse=True)
        for dn in debit_notes_data:
            if dn.timestamp < timestamp:
                return dn
        return None

    async def get_previous_payable_debit_notes_count(self, timestamp: datetime) -> int:
        """Get payable debit note count from before given `timestamp`."""
        debit_notes_data = [(await dn.get_data()) for dn in self.parent.debit_notes]
        return len(
            [
                dn
                for dn in debit_notes_data
                if dn.timestamp < timestamp and dn.payment_due_date is not None
            ]
        )

    @staticmethod
    def validate_mid_agreement_payment(
        payment_props: PaymentProps,
        payment_due_date: Optional[datetime],
        agreement_duration: timedelta,
        previous_payable_debit_notes_count: int,
        grace_period: timedelta = timedelta(seconds=30),
    ) -> None:
        """Validate debit note mid agreement payment data."""
        if payment_due_date is None:
            return

        if (
            payment_props.payment_timeout is None
            or payment_props.debit_notes_accept_timeout is None
        ):
            raise PaymentValidationException(
                "Payable debit note received when mid-agreement payments inactive."
            )

        interval = timedelta(seconds=payment_props.payment_timeout)
        if agreement_duration + grace_period < previous_payable_debit_notes_count * interval:
            raise PaymentValidationException(
                f"Too many debit notes received {previous_payable_debit_notes_count=}. "
                f"{agreement_duration + grace_period}"
                f" < {previous_payable_debit_notes_count  * interval}"
            )

    @classmethod
    def validate_payment_data(
        cls,
        debit_note_data: models.DebitNote,
        previous_debit_note_data: Optional[models.DebitNote],
        previous_payable_debit_notes_count: int,
        agreement_data: "AgreementData",
    ) -> Decimal:
        """Validate debit note payment data.

        Raises: PaymentValidationException
        """
        if agreement_data.agreement_duration is None:
            raise PaymentValidationException("Agreement was not approved")

        payment_props = PaymentProps.from_properties(agreement_data.properties)
        cls.validate_mid_agreement_payment(
            payment_props,
            debit_note_data.payment_due_date,
            agreement_data.agreement_duration,
            previous_payable_debit_notes_count,
        )

        coeffs = LinearCoeffs.from_properties(agreement_data.properties)
        if coeffs is None:
            raise PaymentValidationException("Unable to retrieve coeffs details")

        total_amount_due = eth_decimal(debit_note_data.total_amount_due)
        calculated_cost = validate_payment_calculated_cost(
            coeffs=coeffs,
            amount=total_amount_due,
            usage_counter_vector=debit_note_data.usage_counter_vector,  # type: ignore
        )

        time_since_last_dn = amount_since_last_dn = None
        if previous_debit_note_data:
            time_since_last_dn = debit_note_data.timestamp - previous_debit_note_data.timestamp
            amount_since_last_dn = total_amount_due - eth_decimal(
                previous_debit_note_data.total_amount_due
            )

        max_cost, max_cost_since_last_debit_note = validate_payment_max_cost(
            coeffs=coeffs,
            inf=InfrastructureProps.from_properties(agreement_data.properties),
            duration=agreement_data.agreement_duration,
            amount=total_amount_due,
            time_since_last_debit_note=time_since_last_dn,
            amount_since_last_debit_note=amount_since_last_dn,
        )

        logger.info(
            f"Validation of DebitNote for {agreement_data.agreement_id=} ok "
            f"{total_amount_due=} {calculated_cost=} {max_cost=} {max_cost_since_last_debit_note=}"
        )
        return total_amount_due

    async def validate_and_accept(self, allocation: Allocation) -> None:
        """Validate debit note and accept using a given :any:`Allocation`."""
        debit_note_data = await self.get_data(force=True)
        if debit_note_data.status != PayDocumentStatus.RECEIVED:
            logger.warning(f"Wrong status of debit_note {debit_note_data.status} != RECEIVED")
            return

        agreement_data: "AgreementData" = await self.activity.agreement.get_agreement_data(
            force=True
        )

        previous_debit_note_data = await self.get_previous_debit_note_data(
            debit_note_data.timestamp
        )
        previous_payable_debit_notes_count = await self.get_previous_payable_debit_notes_count(
            debit_note_data.timestamp
        )

        try:
            total_amount_due = self.validate_payment_data(
                debit_note_data,
                previous_debit_note_data,
                previous_payable_debit_notes_count,
                agreement_data,
            )
        except PaymentValidationException:
            logger.warning(f"Debit Note {self.id} validation failed", exc_info=True)
            return

        await self.accept(allocation, total_amount_due)

    async def accept_full(self, allocation: Allocation) -> None:
        """Accept full debit note amount using a given :any:`Allocation`."""
        amount_str = (await self.get_data()).total_amount_due
        await self.accept(allocation, Decimal(amount_str))

    @api_call_wrapper(retry_count=5)
    async def accept(self, allocation: Allocation, amount: Union[Decimal, float]) -> None:
        acceptance = models.Acceptance(
            total_amount_accepted=str(amount), allocation_id=allocation.id
        )
        await self.api.accept_debit_note(self.id, acceptance)
