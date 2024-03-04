import asyncio
import json
import logging
from datetime import timedelta
from decimal import Decimal
from typing import Dict, List, Optional

from ya_payment import ApiException

from golem.managers.base import ManagerException, PaymentManager
from golem.node import GolemNode
from golem.payload.defaults import DEFAULT_PAYMENT_DRIVER, DEFAULT_PAYMENT_NETWORK
from golem.resources import (
    Agreement,
    Allocation,
    DebitNote,
    Invoice,
    NewAgreement,
    NewDebitNote,
    NewInvoice,
)
from golem.utils.logging import trace_span

logger = logging.getLogger(__name__)

# 2 minutes 30 seconds to as it sometimes take extra time to receive Invoice from an agreement
DEFAULT_SHUTDOWN_TIMEOUT: timedelta = timedelta(seconds=150)


class DefaultPaymentManager(PaymentManager):
    def __init__(
        self,
        golem: GolemNode,
        budget: float,
        network: str = DEFAULT_PAYMENT_NETWORK,
        driver: str = DEFAULT_PAYMENT_DRIVER,
        shutdown_timeout: timedelta = DEFAULT_SHUTDOWN_TIMEOUT,
    ):
        self._golem = golem
        self._budget = budget
        self._network = network
        self._driver = driver
        self._shutdown_timeout = shutdown_timeout.total_seconds()

        self._allocation: Optional[Allocation] = None

        self._event_handlers: List = []

        self._agreements: Dict[str, Agreement] = {}
        self._no_agreements_event: asyncio.Event = asyncio.Event()
        self._no_agreements_event.set()

    @trace_span("Starting DefaultPaymentManager", log_level=logging.INFO)
    async def start(self):
        self._event_handlers.extend(
            [
                await self._golem.event_bus.on(NewInvoice, self._handle_invoice_payment),
                await self._golem.event_bus.on(NewDebitNote, self._handle_pay_debit_note_payment),
                await self._golem.event_bus.on(NewAgreement, self._handle_new_agreement),
            ]
        )

    @trace_span("Getting allocation", show_results=True, log_level=logging.INFO)
    async def get_allocation(self) -> Allocation:
        if self._allocation is None:
            self._allocation = await self._create_allocation()

        return self._allocation

    async def _release_allocation(self) -> None:
        if self._allocation is None:
            return

        await self._allocation.release()
        self._allocation = None

    @trace_span()
    async def _create_allocation(self) -> Allocation:
        try:
            return await Allocation.create_any_account(
                self._golem, Decimal(self._budget), self._network, self._driver
            )
        except ApiException as e:
            raise ManagerException(json.loads(e.body)["message"]) from e

    @trace_span("Stopping DefaultPaymentManager", log_level=logging.INFO)
    async def stop(self):
        """Terminate all related agreements."""
        try:
            await asyncio.wait_for(self._wait_for_invoices(), timeout=self._shutdown_timeout)
        except TimeoutError:
            logger.error(
                "Waiting for invoices failed with timeout! Those agreements did not sent invoices:"
                f" {[a for a in self._agreements]}"
            )

        await asyncio.gather(*[agreement.close_all() for agreement in self._agreements.values()])
        self._agreements.clear()

        for event_handler in self._event_handlers:
            await self._golem.event_bus.off(event_handler)
        self._event_handlers.clear()

        await self._release_allocation()

    @trace_span("Waiting for invoices", log_level=logging.INFO)
    async def _wait_for_invoices(self):
        await self._no_agreements_event.wait()

    def _save_agreement(self, agreement: "Agreement") -> None:
        """Add agreement form the pool of known agreements."""
        self._agreements[agreement.id] = agreement
        self._no_agreements_event.clear()
        logger.info(f"Added {agreement.id} to the pool of known agreements")

    def _remove_agreement(self, agreement_id: str) -> None:
        """Remove agreement form the pool of known agreements."""
        del self._agreements[agreement_id]
        if not self._agreements:
            self._no_agreements_event.set()
        logger.info(f"Removed {agreement_id} from the pool of known agreements")

    async def _handle_new_agreement(self, event: NewAgreement) -> None:
        agreement: "Agreement" = event.resource
        self._save_agreement(agreement)

    @trace_span()
    async def _handle_invoice_payment(self, event: NewInvoice) -> None:
        invoice: Invoice = event.resource
        invoice_data = await invoice.get_data()
        if invoice_data.agreement_id not in self._agreements:
            logger.info("Ignoring invoice from unknown agreement `%s`", invoice_data.agreement_id)
            return

        logger.debug("Accepting invoice `%s`: %s", invoice, invoice_data)
        assert self._allocation is not None  # mypy
        await invoice.validate_and_accept(self._allocation)
        self._remove_agreement(invoice_data.agreement_id)

    @trace_span()
    async def _handle_pay_debit_note_payment(self, event: NewDebitNote) -> None:
        debit_note: DebitNote = event.resource
        debit_note_data = await debit_note.get_data()
        if debit_note_data.agreement_id not in self._agreements:
            logger.info(
                "Ignoring debit note from unknown agreement `%s`", debit_note_data.agreement_id
            )
            return

        logger.debug("Accepting debit note `%s`: %s", debit_note, debit_note_data)
        assert self._allocation is not None  # mypy
        await debit_note.validate_and_accept(self._allocation)
