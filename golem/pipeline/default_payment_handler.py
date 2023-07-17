import asyncio
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Set

from golem.resources import NewDebitNote, NewInvoice

if TYPE_CHECKING:
    from golem.node import GolemNode
    from golem.resources import Allocation, NewAgreement


class DefaultPaymentHandler:
    """Accepts all incoming debit_notes and invoices.

    Calls `get_data(force=True)` on invoices/debit notes after they are accepted,
    so appropriate :any:`ResourceDataChanged` event is emitted.

    Usage::

        async with GolemNode() as golem:
            allocation = await golem.create_allocation(BUDGET)
            payment_handler = DefaultPaymentHandler(golem, allocation)

            try:
                #   ... interact with the Golem Network ...
            finally:
                await payment_handler.terminate_agreements()
                await payment_handler.wait_for_invoices()

    """

    def __init__(self, node: "GolemNode", allocation: "Allocation"):
        """Init DefaultPaymentHandler.

        :param node: Debit notes/invoices received by this node will be accepted.
            :any:`DefaultPaymentHandler` will only work if the :any:`GolemNode` was started with
            `collect_payment_events = True`.
        :param allocation: Allocation that will be used to accept debit notes/invoices.
        """

        # FIXME: Resolve local import due to cyclic imports
        from golem.resources import Agreement

        self._node = node
        self.allocation = allocation
        self._agreements: Set[Agreement] = set()

    async def start(self):
        # FIXME: Add event_bus.off

        await self._node.event_bus.on(NewAgreement, self.on_agreement)
        await self._node.event_bus.on(NewInvoice, self.on_invoice)
        await self._node.event_bus.on(NewDebitNote, self.on_debit_note)

    async def on_agreement(self, event: "NewAgreement") -> None:
        # FIXME: Resolve local import due to cyclic imports

        self._agreements.add(event.resource)

    async def on_invoice(self, event: NewInvoice) -> None:
        invoice = event.resource

        if (await invoice.get_data(force=True)).status == "RECEIVED":
            await invoice.accept_full(self.allocation)
            await invoice.get_data(force=True)

    async def on_debit_note(self, event: NewDebitNote) -> None:
        debit_note = event.resource

        if (await debit_note.get_data(force=True)).status == "RECEIVED":
            await debit_note.accept_full(self.allocation)
            await debit_note.get_data(force=True)

    async def terminate_agreements(self) -> None:
        """Terminate all agreements and activities.

        This is intended to be used just before :any:`wait_for_invoices`.
        """
        await asyncio.gather(*[agreement.close_all() for agreement in self._agreements])

    async def wait_for_invoices(self, timeout: float = 5) -> None:
        """Wait for invoices for all agreements and accept them.

        :param timeout: Maximum wait time in seconds.
        """
        stop = datetime.now() + timedelta(seconds=timeout)
        while datetime.now() < stop and any(
            agreement.invoice is None or agreement.invoice.data.status == "RECEIVED"
            for agreement in self._agreements
        ):
            await asyncio.sleep(0.1)

        missing_invoices = [
            agreement for agreement in self._agreements if agreement.invoice is None
        ]
        if missing_invoices:
            missing_invoices_str = ", ".join([str(agreement) for agreement in missing_invoices])
            print(
                f"wait_for_invoices timed out, agreements without invoices: {missing_invoices_str}"
            )
