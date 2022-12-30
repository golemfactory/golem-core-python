from golem_core.low import Allocation, Demand, Agreement, Activity, PoolingBatch, DebitNote
from golem_core.events import NewResource, ResourceClosed

class EventWriter:
    def __init__(self, golem, db):
        self.golem = golem
        self.db = db

    def start(self):
        self.golem.event_bus.resource_listen(
            self._save_new_resource,
            event_classes=[NewResource],
            resource_classes=[Allocation, Demand, Agreement, Activity, PoolingBatch, DebitNote],
        )
        self.golem.event_bus.resource_listen(
            self._save_activity_closed,
            event_classes=[ResourceClosed],
            resource_classes=[Activity],
        )

    async def _save_new_resource(self, event):
        #   NOTE: We have only a single callback (instead of separate callbacks for separate resources)
        #         because the order of the inserts **must** be preserved (because of the foreign keys).
        #         This doesn't matter that much now, but might matter more after
        #         https://github.com/golemfactory/golem-api-python/issues/3
        #   NOTE: When we are recovering, NewResource event is emitted for Agreements/Activities/Batches
        #         that already exist. This probably should be a different event.
        #         https://github.com/golemfactory/golem-api-python/issues/6

        db = self.db
        resource = event.resource
        resource_id = resource.id

        if isinstance(event.resource, Demand):
            await db.aexecute(
                "INSERT INTO demand (id, run_id) VALUES (%(demand_id)s, %(run_id)s)",
                {"demand_id": resource_id})
        elif isinstance(event.resource, Allocation):
            await db.aexecute(
                "INSERT INTO allocation (id, run_id) VALUES (%(demand_id)s, %(run_id)s)",
                {"demand_id": resource_id})
        elif isinstance(event.resource, Agreement):
            if not resource.has_parent:
                #   This is possible on recovery and we already have entry for this Agreement
                return

            proposal = resource.parent
            await db.aexecute("""
                INSERT INTO proposal (id, demand_id) VALUES (%(proposal_id)s, %(demand_id)s);
                INSERT INTO agreement (id, proposal_id) VALUES (%(agreement_id)s, %(proposal_id)s);
            """, {"proposal_id": proposal.id, "demand_id": proposal.demand.id, "agreement_id": resource_id})
        elif isinstance(event.resource, Activity):
            #   Conflict possible when recovering only
            await db.aexecute("""
                INSERT INTO activity (id, agreement_id)
                VALUES (%(activity_id)s, %(agreement_id)s)
                ON CONFLICT DO NOTHING
            """, {"activity_id": resource_id, "agreement_id": resource.parent.id})
        elif isinstance(event.resource, PoolingBatch):
            #   Conflict possible when recovering only
            await db.aexecute("""
                INSERT INTO batch (id, activity_id)
                VALUES (%(batch_id)s, %(activity_id)s)
                ON CONFLICT DO NOTHING
            """, {"batch_id": resource_id, "activity_id": resource.parent.id})
        elif isinstance(event.resource, DebitNote):
            data = await resource.get_data()
            await db.aexecute("""
                INSERT INTO debit_note (id, activity_id, amount)
                VALUES (%(batch_id)s, %(activity_id)s, %(amount)s)
            """, {"batch_id": resource_id, "activity_id": data.activity_id, "amount": data.total_amount_due})

    async def _save_activity_closed(self, event):
        activity_id = event.resource.id

        try:
            self.db.execute("""
                UPDATE  activity
                SET     (status, stop_reason) = ('STOPPED', COALESCE(stop_reason, 'app closing'))
                WHERE   id = %(activity_id)s
            """, {"activity_id": activity_id})
        except Exception as e:
            print(e)
