import asyncio
import psycopg2

from golem_core.low import Demand, Agreement, Activity, PoolingBatch
from golem_core.events import NewResource, ResourceClosed

class EventWriter:
    def __init__(self, golem, db):
        self.golem = golem
        self.db = db

    async def run(self):
        self.golem.event_bus.resource_listen(
            self._save_new_resource,
            event_classes=[NewResource],
            resource_classes=[Demand, Agreement, Activity, PoolingBatch],
        )
        self.golem.event_bus.resource_listen(
            self._save_activity_closed,
            event_classes=[ResourceClosed],
            resource_classes=[Activity],
        )

        #   We just wait here forever now, but in the future we might want to remove
        #   the listiner once run() is cancelled. This doesn't matter now. We could also just return.
        await asyncio.Future()

    async def _save_new_resource(self, event):
        #   NOTE: We have only a single callback (instead of separate callbacks for separate resources)
        #         because the order of the inserts **must** be preserved (because of the foreign keys).
        #         This doesn't matter that much now, but might matter more after
        #         https://github.com/golemfactory/golem-api-python/issues/3
        db = self.db
        resource = event.resource
        resource_id = resource.id

        try:
            if isinstance(event.resource, Demand):
                await db.aexecute("INSERT INTO demand (id, run_id) VALUES (%s, %s)", (resource_id, self.golem.app_session_id))
            elif isinstance(event.resource, Agreement):
                proposal = resource.parent
                await db.aexecute("""
                    INSERT INTO proposal (id, demand_id) VALUES (%(proposal_id)s, %(demand_id)s);
                    INSERT INTO agreement (id, proposal_id) VALUES (%(agreement_id)s, %(proposal_id)s);
                """, {"proposal_id": proposal.id, "demand_id": proposal.demand.id, "agreement_id": resource_id})
            elif isinstance(event.resource, Activity):
                await db.aexecute("INSERT INTO activity (id, agreement_id) VALUES (%s, %s)", (resource_id, resource.parent.id))
            elif isinstance(event.resource, PoolingBatch):
                await db.aexecute("INSERT INTO batch (id, activity_id) VALUES (%s, %s)", (resource_id, resource.parent.id))
        except psycopg2.errors.UniqueViolation:
            #   This is possible when recovering. We discover already existing objects and try to insert them again.
            #   This problem will disappear once we have ResourceCreated/ResourceFound distinction
            #   (described in https://github.com/golemfactory/golem-core-python/issues/6).
            pass

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
