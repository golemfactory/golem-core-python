import asyncio

from golem_api.low import Demand, Proposal, Agreement, Activity, PoolingBatch
from golem_api.events import NewResource


async def save_new_objects(golem, db):
    async def save_resource(event):
        #   NOTE: We have only a single callback (instead of separate callbacks for separate resources)
        #         because the order of the inserts **must** be preserved (because of the foreign keys).
        #         This doesn't matter that much now, but might matter more after
        #         https://github.com/golemfactory/golem-api-python/issues/3
        #   (but also: millions of proposals should not slow down inserting informations about agreements, batches etc
        #    --> this might be a TODO)
        resource = event.resource
        resource_id = resource.id

        if isinstance(event.resource, Demand):
            db.execute("INSERT INTO demand (id, run_id) VALUES (%s, %s)", (resource_id, golem.app_session_id))
        elif isinstance(event.resource, Proposal):
            db.execute("INSERT INTO proposal (id, demand_id) VALUES (%s, %s)", (resource_id, resource.demand.id))
        elif isinstance(event.resource, Agreement):
            db.execute("INSERT INTO agreement (id, proposal_id) VALUES (%s, %s)", (resource_id, resource.parent.id))
        elif isinstance(event.resource, Activity):
            db.execute("INSERT INTO activity (id, agreement_id) VALUES (%s, %s)", (resource_id, resource.parent.id))
        elif isinstance(event.resource, PoolingBatch):
            db.execute("INSERT INTO batch (id, activity_id) VALUES (%s, %s)", (resource_id, resource.parent.id))

    golem.event_bus.resource_listen(
        save_resource,
        event_classes=[NewResource],
        resource_classes=[Demand, Proposal, Agreement, Activity, PoolingBatch],
    )

    await asyncio.Future()
