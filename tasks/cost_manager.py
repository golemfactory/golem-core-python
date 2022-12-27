import asyncio

from golem_core.low import DebitNote
from golem_core.events import NewResource

class CostManager:
    def __init__(self, golem, db, *, result_max_price, init_seconds=10):
        self.golem = golem
        self.db = db
        self.result_max_price = result_max_price
        self.init_seconds = init_seconds

    def start(self):
        self.golem.event_bus.resource_listen(
            self._on_debit_note_event,
            event_classes=[NewResource],
            resource_classes=[DebitNote],
        )

    async def _on_debit_note_event(self, event):
        asyncio.create_task(self._evaluate_activity(event.resource))

    async def _evaluate_activity(self, debit_note):
        await self._wait_for_debit_note_write(debit_note)

        activity_id = (await debit_note.get_data()).activity_id
        try:
            if await self._activity_too_expensive(activity_id):
                await self._stop_activity(activity_id)
        except Exception as e:
            print(e)

    async def _wait_for_debit_note_write(self, debit_note):
        #   Debit note might not yet be saved to the database, and cost aggregates
        #   work only on saved debit notes, so we wait here.
        #   This is pretty ugly but harmless.
        while True:
            await asyncio.sleep(0.1)
            if await self.db.select(
                "SELECT 1 FROM tasks.debit_note WHERE id = %(debit_note_id)s",
                {"debit_note_id": debit_note.id}
            ):
                return

    async def _activity_too_expensive(self, activity_id):
        if await self.db.select("""
            SELECT  1
            FROM    tasks.activity
            WHERE   id = %(activity_id)s
                AND created_ts + %(interval)s::interval > now()
        """, {"activity_id": activity_id, "interval": f"{self.init_seconds} seconds"}):
            #   Grace period
            return False
        return True
        # cost = await self.db.select("""
        #     WITH
        #     batch_result_ratio AS (
        #         WITH
        #         batches AS (
        #             SELECT  count(*) AS cnt
        #             FROM    tasks.batches(%(run_id)s)
        #         ),
        #         results AS (
        #             SELECT  cnt AS results_cnt
        #             FROM    tasks.results
        #             WHERE   run_id = %(run_id)s
        #             ORDER BY created_ts DESC
        #             LIMIT 1
        #         )
        #         SELECT  results.cnt / (batches.cnt + 0.00000001) AS batch_result_ratio
        #         FROM    batches, results
        #     ),
        #     activity_cost_batches AS (
        #         SELECT  
        #     

        #         
        # return True

    async def _stop_activity(self, activity_id):
        await self.db.aexecute("""
            UPDATE  activity
            SET     (status, stop_reason) = ('STOPPING', 'too expensive')
            WHERE   id = %(activity_id)s
                AND status IN ('NEW', 'READY')
        """, {"activity_id": activity_id})
        activity = self.golem.activity(activity_id)
        await activity.parent.close_all()
        await self.db.aexecute(
            "UPDATE activity SET status = 'STOPPED' WHERE id = %(activity_id)s",
            {"activity_id": activity_id})
