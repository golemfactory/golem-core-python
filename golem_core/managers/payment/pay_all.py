import asyncio
import logging
from decimal import Decimal
from typing import Optional

from golem_core.core.golem_node.golem_node import PAYMENT_DRIVER, PAYMENT_NETWORK, GolemNode
from golem_core.core.market_api import AgreementClosed, NewAgreement
from golem_core.core.payment_api.events import NewDebitNote, NewInvoice
from golem_core.core.payment_api.resources.allocation import Allocation
from golem_core.core.payment_api.resources.debit_note import DebitNote
from golem_core.core.payment_api.resources.invoice import Invoice
from golem_core.managers.base import PaymentManager

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

    async def start(self) -> None:
        # TODO: Add stop with event_bus.off()

        await self._golem.event_bus.on(NewInvoice, self._pay_invoice_if_received)
        await self._golem.event_bus.on(NewDebitNote, self._pay_debit_note_if_received)

        await self._golem.event_bus.on(NewAgreement, self._increment_opened_agreements)
        await self._golem.event_bus.on(AgreementClosed, self._increment_closed_agreements)

    async def stop(self) -> None:
        await self.wait_for_invoices()

    async def get_allocation(self) -> "Allocation":
        logger.debug("Getting allocation...")

        if self._allocation is None:
            logger.debug("Creating allocation...")

            self._allocation = await Allocation.create_any_account(
                self._golem, Decimal(self._budget), self._network, self._driver
            )
            self._golem.add_autoclose_resource(self._allocation)

            logger.debug(f"Creating allocation done with `{self._allocation.id}`")

        logger.debug(f"Getting allocation done with `{self._allocation.id}`")

        return self._allocation

    async def wait_for_invoices(self):
        logger.info("Waiting for invoices...")

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

    async def _pay_invoice_if_received(self, event: NewInvoice) -> None:
        logger.debug("Received invoice")

        invoice = event.resource
        assert isinstance(invoice, Invoice)

        if (await invoice.get_data(force=True)).status == "RECEIVED":
            logger.debug(f"Accepting invoice `{invoice.id}`...")

            assert self._allocation is not None  # TODO think of a better way
            await invoice.accept_full(self._allocation)
            await invoice.get_data(force=True)
            self._payed_invoices_count += 1

            logger.debug(f"Accepting invoice `{invoice.id}` done")
            logger.info(f"Invoice `{invoice.id}` accepted")

    async def _pay_debit_note_if_received(self, event: NewDebitNote) -> None:
        logger.debug("Received debit note")

        debit_note = event.resource
        assert isinstance(debit_note, DebitNote)

        if (await debit_note.get_data(force=True)).status == "RECEIVED":
            logger.debug(f"Accepting DebitNote `{debit_note.id}`...")

            assert self._allocation is not None  # TODO think of a better way
            await debit_note.accept_full(self._allocation)
            await debit_note.get_data(force=True)

            logger.debug(f"Accepting DebitNote `{debit_note.id}` done")
            logger.debug(f"DebitNote `{debit_note.id}` accepted")
