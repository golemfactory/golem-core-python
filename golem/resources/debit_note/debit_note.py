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

    async def get_previous_debit_note(self) -> Optional["DebitNote"]:
        """Get previous debit note."""
        return max(
            (dn for dn in self.activity.debit_notes if dn.created_at < self.created_at),
            key=lambda dn: dn.created_at,  # type: ignore[union-attr]
            default=None,
        )

    async def get_previous_payable_debit_note(self) -> Optional["DebitNote"]:
        """Get previous payable debit note."""
        return max(
            [
                dn
                for dn in self.activity.debit_notes
                if dn.created_at < self.created_at
                and (await dn.get_data()).payment_due_date is not None
            ],
            key=lambda dn: dn.created_at,  # type: ignore[union-attr]
            default=None,
        )

    @staticmethod
    def validate_mid_agreement_payment(
        activity_created_at: datetime,
        debit_note_created_at: datetime,
        payment_props: PaymentProps,
        payment_due_date: Optional[datetime],
        previous_debit_note_created_at: Optional[datetime] = None,
        previous_payable_debit_note_created_at: Optional[datetime] = None,
        payment_timeout_grace_period: timedelta = timedelta(minutes=5),
        debit_note_interval_grace_period: timedelta = timedelta(seconds=30),
    ) -> None:
        """Validate debit note mid agreement payment data."""
        if payment_due_date is None:
            return

        if payment_props.payment_timeout is None or payment_props.debit_note_interval is None:
            raise PaymentValidationException(
                "Payable debit note received when mid-agreement payments inactive."
            )

        payment_timeout_timedelta = timedelta(seconds=payment_props.payment_timeout)

        received_payment_timeout = payment_due_date - debit_note_created_at
        if received_payment_timeout + payment_timeout_grace_period < payment_timeout_timedelta:
            raise PaymentValidationException(
                f"Payment timeout is shorter than agreed {payment_due_date=}"
                f"{received_payment_timeout=} < {payment_timeout_timedelta=}."
            )

        time_since_last_payable_debit_note = debit_note_created_at - (
            previous_payable_debit_note_created_at
            if previous_payable_debit_note_created_at
            else activity_created_at
        )
        if (
            time_since_last_payable_debit_note + payment_timeout_grace_period
            < payment_timeout_timedelta
        ):
            raise PaymentValidationException(
                f"Time since last payable debit note {time_since_last_payable_debit_note}"
                f"exceeds agreed timeout {payment_timeout_timedelta=}"
            )

        debit_note_interval_timedelta = timedelta(seconds=payment_props.debit_note_interval)
        time_since_last_debit_note = (
            (debit_note_created_at - previous_debit_note_created_at)
            if previous_debit_note_created_at
            else None
        )
        if (
            time_since_last_debit_note is not None
            and time_since_last_debit_note + debit_note_interval_grace_period
            < debit_note_interval_timedelta
        ):
            raise PaymentValidationException(
                f"Too many debit notes received {time_since_last_debit_note=}"
                f" {debit_note_interval_timedelta=}"
            )

    def validate_payment_data(
        self,
        debit_note_data: models.DebitNote,
        previous_debit_note: Optional["DebitNote"],
        previous_payable_debit_note: Optional["DebitNote"],
        agreement_data: "AgreementData",
    ) -> Decimal:
        """Validate debit note payment data.

        Raises: PaymentValidationException
        """
        if agreement_data.agreement_duration is None:
            raise PaymentValidationException("Agreement was not approved")

        payment_props = PaymentProps.from_properties(agreement_data.properties)
        self.validate_mid_agreement_payment(
            self.activity.created_at,
            self.created_at,
            payment_props,
            debit_note_data.payment_due_date,
            previous_debit_note.created_at if previous_debit_note else None,
            previous_payable_debit_note.created_at if previous_payable_debit_note else None,
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
        if previous_debit_note:
            time_since_last_dn = self.created_at - previous_debit_note.created_at
            amount_since_last_dn = total_amount_due - eth_decimal(
                previous_debit_note.data.total_amount_due
            )

        max_cost, max_cost_since_last_debit_note = validate_payment_max_cost(
            coeffs=coeffs,
            inf=InfrastructureProps.from_properties(agreement_data.properties),
            duration=self.created_at - self.activity.created_at,
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

        previous_debit_note = await self.get_previous_debit_note()
        previous_payable_debit_note = await self.get_previous_payable_debit_note()

        try:
            total_amount_due = self.validate_payment_data(
                debit_note_data,
                previous_debit_note,
                previous_payable_debit_note,
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
