import asyncio
import logging
from decimal import Decimal
from typing import List, Optional

from golem.managers.base import PaymentManager
from golem.node import PAYMENT_DRIVER, PAYMENT_NETWORK, GolemNode
from golem.resources import (
    AgreementClosed,
    Allocation,
    DebitNote,
    Invoice,
    NewAgreement,
    NewDebitNote,
    NewInvoice,
)
from golem.utils.logging import trace_span

logger = logging.getLogger(__name__)


class PayAllPaymentManager(PaymentManager):
    def __init__(
        self,
        golem: GolemNode,
        budget: float,
        network: str = PAYMENT_NETWORK,
        driver: str = PAYMENT_DRIVER,
    ):
        self._golem = golem
        self._budget = budget
        self._network = network
        self._driver = driver

        self._allocation: Optional[Allocation] = None

        self._opened_agreements_count = 0
        self._closed_agreements_count = 0
        self._payed_invoices_count = 0

        self._event_handlers: List = []

    @trace_span()
    async def start(self):
        # TODO: Add stop with event_bus.off()
        self._event_handlers.extend(
            [
                await self._golem.event_bus.on(NewInvoice, self._pay_invoice_if_received),
                await self._golem.event_bus.on(NewDebitNote, self._pay_debit_note_if_received),
                await self._golem.event_bus.on(NewAgreement, self._increment_opened_agreements),
                await self._golem.event_bus.on(AgreementClosed, self._increment_closed_agreements),
            ]
        )

    @trace_span()
    async def stop(self):
        await self.wait_for_invoices()

        for event_handler in self._event_handlers:
            await self._golem.event_bus.off(event_handler)

    @trace_span()
    async def _create_allocation(self) -> None:
        self._allocation = await Allocation.create_any_account(
            self._golem, Decimal(self._budget), self._network, self._driver
        )

        # TODO: We should not rely on golem node with cleanups, manager should do it by itself
        self._golem.add_autoclose_resource(self._allocation)

    @trace_span(show_results=True)
    async def get_allocation(self) -> "Allocation":
        # TODO handle NoMatchingAccount
        if self._allocation is None:
            await self._create_allocation()

        # TODO fix type
        return self._allocation  # type: ignore[return-value]

    @trace_span()
    async def wait_for_invoices(self):
        for _ in range(60):
            await asyncio.sleep(1)
            if (
                self._opened_agreements_count
                == self._closed_agreements_count
                == self._payed_invoices_count
            ):
                logger.info("Waiting for invoices done with all paid")
                return

        # TODO: Add list of agreements without payment
        logger.warning("Waiting for invoices failed with timeout!")

    async def _increment_opened_agreements(self, event: NewAgreement):
        self._opened_agreements_count += 1

    async def _increment_closed_agreements(self, event: AgreementClosed):
        self._closed_agreements_count += 1

    @trace_span(show_arguments=True)
    async def _accept_invoice(self, invoice: Invoice) -> None:
        assert self._allocation is not None  # TODO think of a better way
        await invoice.accept_full(self._allocation)
        await invoice.get_data(force=True)
        self._payed_invoices_count += 1

        logger.info(f"Invoice `{invoice.id}` accepted")

    @trace_span(show_arguments=True)
    async def _accept_debit_note(self, debit_note: DebitNote) -> None:
        assert self._allocation is not None  # TODO think of a better way
        await debit_note.accept_full(self._allocation)
        await debit_note.get_data(force=True)

        logger.info(f"DebitNote `{debit_note.id}` accepted")

    @trace_span()
    async def _pay_invoice_if_received(self, event: NewInvoice) -> None:
        invoice = event.resource

        if (await invoice.get_data(force=True)).status == "RECEIVED":
            await self._accept_invoice(invoice)

    @trace_span()
    async def _pay_debit_note_if_received(self, event: NewDebitNote) -> None:
        debit_note = event.resource

        if (await debit_note.get_data(force=True)).status == "RECEIVED":
            await self._accept_debit_note(debit_note)