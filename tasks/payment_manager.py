import asyncio
from datetime import datetime, timedelta

from golem_core.events import NewResource
from golem_core.low import Agreement, Allocation, DebitNote, Invoice

class PaymentManager:
    def __init__(self, golem, db):
        self.golem = golem

        self._allocations = []
        self._agreement_has_invoice = {}

    def start(self):
        self.golem.event_bus.resource_listen(
            self._save_allocation,
            event_classes=[NewResource],
            resource_classes=[Allocation],
        )
        self.golem.event_bus.resource_listen(
            self._save_agreement,
            event_classes=[NewResource],
            resource_classes=[Agreement],
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

    async def _save_agreement(self, event):
        agreement_id = event.resource.id
        if agreement_id not in self._agreement_has_invoice:
            self._agreement_has_invoice[agreement_id] = False

    async def _process_debit_note(self, event):
        debit_note = event.resource
        allocation = self._get_allocation()
        await debit_note.accept_full(allocation)

    async def _process_invoice(self, event):
        invoice = event.resource
        allocation = self._get_allocation()
        await invoice.accept_full(allocation)

        agreement_id = (await invoice.get_data()).agreement_id
        self._agreement_has_invoice[agreement_id] = True

    async def terminate_agreements(self):
        print("Terminating agreements")
        agreements = [
            self.golem.agreement(id_) for id_, finished in self._agreement_has_invoice.items() if not finished
        ]
        tasks = [asyncio.create_task(agreement.close_all()) for agreement in agreements]
        await asyncio.gather(*tasks)
        print("All agreements terminated")

    async def wait_for_invoices(self):
        end = datetime.now() + timedelta(seconds=5)
        while not all(self._agreement_has_invoice.values()) and datetime.now() < end:
            await asyncio.sleep(0.1)
        print("Waiting for invoices finished")

    def _get_allocation(self):
        try:
            return self._allocations[-1]
        except IndexError:
            #   FIXME - this requires some thinking about whole allocation concept.
            #           E.g. maybe we could just create a new allocation here?
            print("No allocation - can't process debit note/invoice")
