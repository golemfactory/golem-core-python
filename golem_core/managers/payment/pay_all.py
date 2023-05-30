import asyncio
import logging
from decimal import Decimal
from typing import Optional

from golem_core.core.golem_node.golem_node import PAYMENT_DRIVER, PAYMENT_NETWORK, GolemNode
from golem_core.core.payment_api.resources.allocation import Allocation
from golem_core.core.payment_api.resources.debit_note import DebitNote
from golem_core.core.payment_api.resources.invoice import Invoice
from golem_core.core.resources.events import NewResource
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

        self._golem.event_bus.resource_listen(self.on_invoice_received, [NewResource], [Invoice])
        self._golem.event_bus.resource_listen(
            self.on_debit_note_received, [NewResource], [DebitNote]
        )

    async def get_allocation(self) -> "Allocation":
        logger.info("Getting allocation...")
        if self._allocation is None:
            logger.info("Creating allocation...")
            self._allocation = await Allocation.create_any_account(
                self._golem, Decimal(self._budget), self._network, self._driver
            )
            self._golem.add_autoclose_resource(self._allocation)
            logger.info("Creating allocation done")
        logger.info("Getting allocation done")
        return self._allocation

    async def on_invoice_received(self, invoice_event: NewResource) -> None:
        logger.info("Received invoice...")
        invoice = invoice_event.resource
        assert isinstance(invoice, Invoice)
        if (await invoice.get_data(force=True)).status == "RECEIVED":
            logger.info("Accepting invoice...")
            assert self._allocation is not None  # TODO think of a better way
            await invoice.accept_full(self._allocation)
            await invoice.get_data(force=True)
            logger.info("Accepting invoice done")

    async def on_debit_note_received(self, debit_note_event: NewResource) -> None:
        logger.info("Received debit note...")
        debit_note = debit_note_event.resource
        assert isinstance(debit_note, DebitNote)
        if (await debit_note.get_data(force=True)).status == "RECEIVED":
            logger.info("Accepting debit note...")
            assert self._allocation is not None  # TODO think of a better way
            await debit_note.accept_full(self._allocation)
            await debit_note.get_data(force=True)
            logger.info("Accepting debit note done")

    async def wait_for_invoices(self):
        logger.info("Waiting for invoices...")
        await asyncio.sleep(30)
        logger.info("Waiting for invoices done")
