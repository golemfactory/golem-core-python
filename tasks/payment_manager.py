import asyncio
from datetime import datetime, timedelta

from ya_payment.exceptions import ApiException

from golem_core.events import NewResource
from golem_core.low import Agreement, DebitNote, Invoice

class BudgetExhausted(Exception):
    def __init__(self, allocation):
        self.allocation = allocation
        super().__init__("Couldn't accept a debit note - current allocation is exhausted")

class PaymentManager:
    def __init__(self, golem, db):
        self.golem = golem

        self._allocation = None
        self._allocation_created_ts = None
        self._budget_exahusted = False

        self._agreement_has_invoice = {}

    async def run(self):
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

        await self._create_allocation()

        while True:
            if self._budget_exahusted:
                await self._allocation.get_data(force=True)
                raise BudgetExhausted(self._allocation)
            if self._allocation_too_old():
                old_allocation = self._allocation
                await self._create_allocation()
                await old_allocation.release()
            await asyncio.sleep(1)

    async def _create_allocation(self):
        self._allocation = await self.golem.create_allocation(amount=0.00001)
        self._allocation_created_ts = datetime.now()

    def _allocation_too_old(self):
        return False

    async def _save_agreement(self, event):
        agreement_id = event.resource.id
        if agreement_id not in self._agreement_has_invoice:
            self._agreement_has_invoice[agreement_id] = False

    async def _process_debit_note(self, event):
        debit_note = event.resource
        try:
            await debit_note.accept_full(self._allocation)
        except ApiException as e:
            if e.status == 400 and "Not enough funds" in str(e):
                self._budget_exahusted = True
            else:
                raise

    async def _process_invoice(self, event):
        invoice = event.resource
        await invoice.accept_full(self._allocation)

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
