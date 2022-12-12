import asyncio

from golem_core.low import Demand, Agreement, Activity, PoolingBatch
from golem_core.events import NewResource


async def save_new_objects(golem, db):
    async def save_resource(event):
        #   NOTE: We have only a single callback (instead of separate callbacks for separate resources)
        #         because the order of the inserts **must** be preserved (because of the foreign keys).
        #         This doesn't matter that much now, but might matter more after
        #         https://github.com/golemfactory/golem-api-python/issues/3
        resource = event.resource
        resource_id = resource.id

        if isinstance(event.resource, Demand):
            db.execute("INSERT INTO demand (id, run_id) VALUES (%s, %s)", (resource_id, golem.app_session_id))
        elif isinstance(event.resource, Agreement):
            proposal = resource.parent
            db.execute("""
                INSERT INTO proposal (id, demand_id) VALUES (%(proposal_id)s, %(demand_id)s);
                INSERT INTO agreement (id, proposal_id) VALUES (%(agreement_id)s, %(proposal_id)s);
            """, {"proposal_id": proposal.id, "demand_id": proposal.demand.id, "agreement_id": resource_id})
        elif isinstance(event.resource, Activity):
            db.execute("INSERT INTO activity (id, agreement_id) VALUES (%s, %s)", (resource_id, resource.parent.id))
        elif isinstance(event.resource, PoolingBatch):
            db.execute("INSERT INTO batch (id, activity_id) VALUES (%s, %s)", (resource_id, resource.parent.id))

    golem.event_bus.resource_listen(
        save_resource,
        event_classes=[NewResource],
        resource_classes=[Demand, Agreement, Activity, PoolingBatch],
    )

    await asyncio.Future()
