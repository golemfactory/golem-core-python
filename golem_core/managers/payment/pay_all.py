from golem_core.managers.base import PaymentManager


class PayAllPaymentManager(PaymentManager):
    def __init__(self, budget, event_bus):
        self._budget = budget
        self._event_bus = event_bus

        self._allocation = Allocation.create(budget=self._budget)

        event_bus.register(InvoiceReceived(allocation=self._allocation), self.on_invoice_received)
        event_bus.register(
            DebitNoteReceived(allocation=self._allocation), self.on_debit_note_received
        )

    def get_allocation(self) -> "Allocation":
        return self._allocation

    def on_invoice_received(self, invoice: "Invoice") -> None:
        invoice.pay()

    def on_debit_note_received(self, debit_note: "DebitNote") -> None:
        debit_note.pay()
