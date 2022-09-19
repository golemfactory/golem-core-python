import asyncio
from datetime import datetime, timedelta

from golem_api.events import NewResource
from golem_api.low import Agreement, Allocation, DebitNote, Invoice
from golem_api import GolemNode

from typing import Set


class DefaultPaymentManager:
    """Accepts all new (i.e. having a RECEIVED status) invoices and debit notes.

    Calls `get_data(force=True)` on invoices/debit notes after their status changes,
    so appropriate ResourceDataChanged event is emitted.

    TODO: this will be extended with `reject_for(activity/agreeement)` in
          the close future
    """
    def __init__(self, node: GolemNode, allocation: Allocation):
        self.allocation = allocation
        self._agreements: Set[Agreement] = set()

        node.event_bus.resource_listen(self.on_agreement, [NewResource], [Agreement])
        node.event_bus.resource_listen(self.on_invoice, [NewResource], [Invoice])
        node.event_bus.resource_listen(self.on_debit_note, [NewResource], [DebitNote])

    async def on_agreement(self, event: NewResource) -> None:
        agreement = event.resource
        assert isinstance(agreement, Agreement)
        self._agreements.add(agreement)

    async def on_invoice(self, event: NewResource) -> None:
        invoice = event.resource
        assert isinstance(invoice, Invoice)
        if (await invoice.get_data(force=True)).status == 'RECEIVED':  # type: ignore
            await invoice.accept_full(self.allocation)
            await invoice.get_data(force=True)

    async def on_debit_note(self, event: NewResource) -> None:
        debit_note = event.resource
        assert isinstance(debit_note, DebitNote)
        if (await debit_note.get_data(force=True)).status == 'RECEIVED':  # type: ignore
            await debit_note.accept_full(self.allocation)
            await debit_note.get_data(force=True)

    async def terminate_agreements(self) -> None:
        await asyncio.gather(*[agreement.terminate() for agreement in self._agreements])

    async def wait_for_invoices(self, timeout: float = 5):
        stop = datetime.now() + timedelta(seconds=timeout)
        while datetime.now() < stop and any(agreement.invoice is None for agreement in self._agreements):
            await asyncio.sleep(0.1)

        missing_invoices = [agreement for agreement in self._agreements if agreement.invoice is None]
        if missing_invoices:
            missing_invoices_str = ", ".join([str(agreement) for agreement in missing_invoices])
            print(f"wait_for_invoices timed out, agreements without invoices: {missing_invoices_str}")
