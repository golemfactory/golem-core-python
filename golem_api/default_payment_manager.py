from golem_api.events import ResourceEvent, NewResource
from golem_api.low import Allocation, DebitNote, Invoice


class DefaultPaymentManager:
    """Accepts all new (i.e. having a RECEIVED status) invoices and debit notes.

    Calls `get_data(force=True)` on invoices/debit notes after their status changes,
    so appropriate ResourceDataChanged event is emitted.

    TODO: this will be extended with `reject_for(activity/agreeement)` in
          the close future
    """
    def __init__(self, allocation: Allocation):
        self.allocation = allocation

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
