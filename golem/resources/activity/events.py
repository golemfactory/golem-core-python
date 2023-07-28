from typing import TYPE_CHECKING

from golem.resources.events import NewResource, ResourceClosed, ResourceDataChanged

if TYPE_CHECKING:
    from golem.resources.activity.activity import Activity  # noqa


class NewActivity(NewResource["Activity"]):
    pass


class ActivityDataChanged(ResourceDataChanged["Activity"]):
    pass


class ActivityClosed(ResourceClosed["Activity"]):
    pass
