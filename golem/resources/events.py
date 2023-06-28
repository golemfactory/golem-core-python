from abc import ABC
from typing import TYPE_CHECKING, Any, Dict, Generic, Tuple, TypeVar

from golem.event_bus import Event

if TYPE_CHECKING:
    from golem.resources.base import Resource  # noqa

TResourceEvent = TypeVar("TResourceEvent", bound="ResourceEvent")
TResource = TypeVar("TResource", bound="Resource")


class ResourceEvent(Event, ABC, Generic[TResource]):
    """Base class for all events related to a particular :any:`Resource`."""

    def __init__(self, resource: TResource):
        self._resource = resource

    @property
    def resource(self) -> TResource:
        """Resource related to this :class:`ResourceEvent`."""
        return self._resource

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.resource})"


class NewResource(ResourceEvent[TResource], ABC, Generic[TResource]):
    """Emitted when a new :any:`Resource` object is created.

    There are three distinct scenarios possible:

    * We create a new resource, e.g. with :any:`GolemNode.create_allocation()`
    * We start interacting with some resource that was created by us before,
      but not with this particular GolemNode instance, eg. :any:`GolemNode.allocation()`
    * We find a resource created by someone else (e.g. a :any:`Proposal` or a :any:`DebitNote`)

    There's no difference between these scenarios from the POV of this event.
    """


class ResourceDataChanged(ResourceEvent[TResource], Generic[TResource]):
    """Emitted when `data` attribute of a :any:`Resource` changes.

    This event is **not** emitted when the data "would have changed if we
    requested new data, but we didn't request it". In other words, we don't listen for
    `yagna`-side changes, only react to changes already noticed in the context of a
    :any:`GolemNode`.

    Second argument is the old data (before the change), so comparing
    `event.resource.data` with `event.old_data` shows what changed.

    NULL (i.e. empty) change doesn't trigger the change, even if we explicitly sent a
    resource-changing call.
    """

    def __init__(self, resource: TResource, old_data: Any):
        super().__init__(resource)
        self._old_data = old_data

        #   TODO: this should be included in typing, but I don't know how to do this
        assert old_data is None or type(resource.data) is type(old_data)

    @property
    def old_data(self) -> Any:
        """Value of `self.resource.data` before the change."""
        return self._old_data

    def diff(self) -> Dict[str, Tuple[Any, Any]]:
        """Return a dictionary {property_name: (old_val, new_val)} with all values that changed."""
        old_dict = self.old_data.to_dict()
        new_dict = self.resource.data.to_dict()
        diff_dict = {}

        for key in old_dict.keys():
            old_val = old_dict[key]
            new_val = new_dict[key]
            if old_val != new_val:
                diff_dict[key] = (old_val, new_val)

        return diff_dict

    def __repr__(self) -> str:
        diff = []
        for key, (old_val, new_val) in self.diff().items():
            diff.append(f"{key}: {old_val} -> {new_val}")
        diff_str = ", ".join(diff)
        return f"{type(self).__name__}({self.resource}, {diff_str})"


class ResourceClosed(ResourceEvent[TResource], Generic[TResource]):
    """Emitted when a resource is deleted or rendered unusable.

    Usual case is when we delete a resource (e.g. :any:`Allocation.release()`),
    or when the lifespan of a resource ends (e.g. :any:`Agreement.terminate()`),
    but this can be also emitted when we notice that resource was deleted by someone
    else (TODO: when? is this possible at all? e.g. expired proposal?).

    This is emitted only when something changes. Creating a new Resource object
    for an already closed resource (e.g. by passing an id of a terminated agreement to
    :any:`GolemNode.agreement`) does not trigger this event.

    This event should never be emitted more than once for a given :any:`Resource`.
    Currently this is not true for :any:`Activity` - this is a known TODO
    (https://github.com/golemfactory/golem-core-python/issues/33).

    Not all resources are closed, e.g. :any:`PoolingBatch` is not.
    """
