from golem_core.managers.base import WorkContext


async def default_on_activity_start(context: WorkContext):
    batch = await context.create_batch()
    batch.deploy()
    batch.start()
    await batch()
    print("activity start")

    # TODO: After this function call we should have check if activity is actually started


async def default_on_activity_stop(context: WorkContext):
    await context.terminate()
    print("activity stop")

    # TODO: After this function call we should have check if activity is actually terminated
