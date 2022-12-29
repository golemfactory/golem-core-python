import asyncio
from datetime import datetime, timedelta
from decimal import Decimal

from golem_core.events import NewResource
from golem_core.low import Agreement, DebitNote, Invoice

class BudgetExhausted(Exception):
    def __init__(self, hourly_budget):
        self.hourly_budget = hourly_budget

        msg = f"Couldn't accept a debit note - got debit notes for more than {hourly_budget} in the last hour"
        super().__init__(msg)

class PaymentManager:
    def __init__(self, golem, db, budget_str):
        self.golem = golem
        self.db = db

        #   NOTE: Now we have a hardcoded logic "budget is specified hourly".
        #         This might ofc change in the future, this logic is contained in PaymentManager fully.
        self.hourly_budget = self._parse_budget_str(budget_str)

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
                raise BudgetExhausted(self.hourly_budget)

            #   Recreate allocation every hour
            if (datetime.now() - self._allocation_created_ts).seconds > 3600:
                old_allocation = self._allocation
                await self._create_allocation()
                await old_allocation.release()
            await asyncio.sleep(1)

    async def _create_allocation(self):
        self._allocation = await self.golem.create_allocation(amount=self.hourly_budget)
        self._allocation_created_ts = datetime.now()

    async def _save_agreement(self, event):
        agreement_id = event.resource.id
        if agreement_id not in self._agreement_has_invoice:
            self._agreement_has_invoice[agreement_id] = False

    async def _process_debit_note(self, event):
        #   Q: Why not just try to accept the debit note and react to failure?
        #   A: Because yagna doesn't enforce the limit. You can use allocation for amount X to accept
        #      any number of debit notes, as long as each of them is below X.
        #      (X is decreased with every accepted **invoice**, but not debit note)
        #
        #   This is **probably** a `yagna` bug (waiting for an answer). Allocation-based implementation
        #   would be much prettier and we'll probably want to go towards it.
        #
        #   Q: Why not gather "activity_id -> amount" map in-memory?
        #   A: Because this logic should be preserved on restarts.
        debit_note = event.resource
        await debit_note.get_data()

        try:
            last_hour_amount = await self._last_hour_amount(debit_note)

            if last_hour_amount > self.hourly_budget:
                self._budget_exahusted = True
                print(f"Failed to accept {debit_note} because {last_hour_amount} > {self.hourly_budget}")
            else:
                await debit_note.accept_full(self._allocation)
        except Exception as e:
            print(e)

    async def _last_hour_amount(self, debit_note):
        #   TODO: This logic might require additional check (but I still hope we'll not need
        #         this SQL at all because necessary logic will be in `debit_note.accept_full`.
        #   NOTE: We have the debit note here (and treat the related activity_id differently) because
        #         we don't know if this debit note is already in the database or not.
        activity_id = debit_note.data.activity_id

        data = await self.db.select("""
            WITH
            this_run_debit_notes AS (
                SELECT  d.id,
                        d.created_ts,
                        d.activity_id,
                        d.amount
                FROM    tasks.debit_note             d
                JOIN    tasks.activities(%(run_id)s) a
                    ON  d.activity_id = a.activity_id
            ),
            hour_ago_sum AS (
                WITH
                activity_max AS (
                    SELECT  activity_id,
                            max(amount) AS amount
                    FROM    this_run_debit_notes
                    WHERE   created_ts + '1 hour'::interval < now()
                    GROUP BY 1
                )
                SELECT  coalesce(sum(amount), 0) AS amount
                FROM    activity_max
            ),
            sum_without_activity AS (
                WITH
                activity_max AS (
                    SELECT  activity_id,
                            max(amount) AS amount
                    FROM    this_run_debit_notes
                    WHERE   activity_id != %(activity_id)s
                    GROUP BY 1
                )
                SELECT  coalesce(sum(amount), 0) AS amount
                FROM    activity_max
            )
            SELECT  sum_without_activity.amount - hour_ago_sum.amount
            FROM    sum_without_activity, hour_ago_sum
        """, {"activity_id": activity_id})

        #   NOTE: data[0][0] might be even negative (e.g. if we have only a single
        #         activity for more than an hour) - this should still work fine

        return data[0][0] + Decimal(debit_note.data.total_amount_due)

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

    @staticmethod
    def _parse_budget_str(budget_str):
        try:
            amount, period = budget_str.split("/")
            assert period == "h"
            return float(amount)
        except Exception:
            raise ValueError(f"Invalid budget: {budget_str}. Example accepted values: '7/h', '0.7/h', '.7/h'")
