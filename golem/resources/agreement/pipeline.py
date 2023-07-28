from golem.resources.activity import Activity
from golem.resources.agreement.agreement import Agreement


async def default_create_activity(agreement: Agreement) -> Activity:
    """Create a new :any:`Activity` for a given :any:`Agreement`."""
    return await agreement.create_activity()
