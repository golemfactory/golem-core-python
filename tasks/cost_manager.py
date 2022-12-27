import asyncio

from golem_core.low import DebitNote
from golem_core.events import NewResource

class CostManager:
    def __init__(self, golem, db, *, result_max_price, init_seconds=300):
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
            if await self._activity_old_enough(activity_id):
                result_price = await self._activity_result_price(activity_id)
                if result_price is not None and result_price > self.result_max_price:
                    await self._stop_activity(activity_id)
        except Exception as e:
            print(e)

    async def _wait_for_debit_note_write(self, debit_note):
        #   Debit note might not yet be saved to the database, and cost aggregates
        #   work only on saved debit notes, so we wait here.
        #   This is pretty ugly but harmless (debit note should be saved ~~ immediately,
        #   so the query will be executed more than once only in extraordinary cases)
        while True:
            await asyncio.sleep(0.1)
            if await self.db.select(
                "SELECT 1 FROM tasks.debit_note WHERE id = %(debit_note_id)s",
                {"debit_note_id": debit_note.id}
            ):
                return

    async def _activity_old_enough(self, activity_id):
        return bool(await self.db.select("""
            SELECT  1
            FROM    tasks.activity
            WHERE   id = %(activity_id)s
                AND created_ts + %(interval)s::interval < now()
        """, {"activity_id": activity_id, "interval": f"{self.init_seconds} seconds"}))

    async def _activity_result_price(self, activity_id):
        return 7

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
