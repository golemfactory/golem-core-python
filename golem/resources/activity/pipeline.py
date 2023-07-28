from golem.resources.activity.activity import Activity
from golem.resources.activity.commands import Deploy, Start


# TODO: Move default functions to Activity class
async def default_prepare_activity(activity: Activity) -> Activity:
    """Execute Deploy() and Start() commands on a given :any:`Activity` and return the same \
    :any:`Activity`.

    If the commands fail, destroys the :any:`Activity` and terminates the corresponding
    :any:`Agreement`.
    """
    try:
        batch = await activity.execute_commands(Deploy(), Start())
        await batch.wait(timeout=300)
        assert batch.success, batch.events[-1].message
    except Exception:
        await activity.parent.close_all()
        raise
    return activity
