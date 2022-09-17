from golem_api.events import ResourceEvent, NewResource
from golem_api.low import Allocation, DebitNote, Invoice


#   NOTE: alternative approach would be to emit these events in
#   Invoice.accept()/DebitNote.accept() methods, but I think this is better:
#   *   Set of events is related to the PaymentManager and different PaymentManagers could
#       have different events - we don't want to have multiple events hardcoded in low-level api
class InvoiceAccepted(ResourceEvent):
    pass


class DebitNoteAccepted(ResourceEvent):
    pass


class DefaultPaymentManager:
    """Accepts all new (i.e. having a RECEIVED status) invoices and debit notes.

    Emits events: :any:`InvoiceAccepted`, :any:`DebitNoteAccepted`.
    Calls `get_data(force=true)` on invoices/debit notes after they were accepted.

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

            invoice.node.event_bus.emit(InvoiceAccepted(invoice))

            await invoice.get_data(force=True)

    async def on_debit_note(self, event: NewResource) -> None:
        debit_note = event.resource
        assert isinstance(debit_note, DebitNote)
        if (await debit_note.get_data(force=True)).status == 'RECEIVED':  # type: ignore
            await debit_note.accept_full(self.allocation)

            debit_note.node.event_bus.emit(DebitNoteAccepted(debit_note))

            await debit_note.get_data(force=True)
