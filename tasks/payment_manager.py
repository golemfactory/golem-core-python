from golem_core.events import NewResource
from golem_core.low import Allocation, DebitNote, Invoice

class PaymentManager:
    def __init__(self, golem, db):
        self.golem = golem

        self._allocations = []

    async def run(self):
        self.golem.event_bus.resource_listen(
            self._save_allocation,
            event_classes=[NewResource],
            resource_classes=[Allocation],
        )
        self.golem.event_bus.resource_listen(
            self._process_debit_note,
            event_classes=[NewResource],
            resource_classes=[DebitNote],
        )
        self.golem.event_bus.resource_listen(
            self._process_invoice,
            event_classes=[NewResource],
            resource_classes=[Invoice],
        )

    async def _save_allocation(self, event):
        allocation = event.resource
        self._allocations.append(allocation)

    async def _process_debit_note(self, event):
        debit_note = event.resource
        allocation = self._get_allocation()
        await debit_note.accept_full(allocation)

    async def _process_invoice(self, event):
        invoice = event.resource
        allocation = self._get_allocation()
        await invoice.accept_full(allocation)

    def _get_allocation(self):
        try:
            return self._allocations[-1]
        except IndexError:
            #   FIXME - this requires some thinking about whole allocation concept.
            #           E.g. maybe we could just create a new allocation here?
            print("No allocation - can't process debit note/invoice")
