from golem_api.events import ResourceEvent, NewResource
from golem_api.low import Allocation


#   NOTE: alternative approach would be to emit these events in
#   Invoice.accept()/DebitNote.accept() methods, but I think this is better:
#   *   They could emit a generic ResourceDataChanged
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

    async def on_invoice(self, event: NewResource):
        invoice = event.resource
        if (await invoice.get_data(force=True)).status == 'RECEIVED':
            await invoice.accept_full(self.allocation)

            invoice.node.event_bus.emit(InvoiceAccepted(invoice))

            await invoice.get_data(force=True)
            print("STATUS IN", invoice.data.status)

    async def on_debit_note(self, event: NewResource):
        debit_note = event.resource
        if (await debit_note.get_data(force=True)).status == 'RECEIVED':
            await debit_note.accept_full(self.allocation)

            debit_note.node.event_bus.emit(DebitNoteAccepted(debit_note))

            await debit_note.get_data(force=True)
            print("STATUS DN", debit_note.data.status)
