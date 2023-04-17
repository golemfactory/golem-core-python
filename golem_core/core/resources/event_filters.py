from dataclasses import dataclass
from typing import Tuple, Type, TYPE_CHECKING

from golem_core.core.events import EventFilter, Event

if TYPE_CHECKING:
    from golem_core.core.resources import ResourceEvent, Resource


@dataclass(frozen=True)
class ResourceEventFilter(EventFilter):
    """ResourceEvents with optional filters by event class/resource type/resource id"""
    event_classes: Tuple[Type['ResourceEvent'], ...]
    resource_classes: Tuple[Type['Resource'], ...]
    resource_ids: Tuple[str, ...]

    def includes(self, event: Event) -> bool:
        # FIXME: Get rid of local import
        from golem_core.core.resources import ResourceEvent

        if not isinstance(event, ResourceEvent):
            return False

        event_class_match = not self.event_classes or any(isinstance(event, cls) for cls in self.event_classes)
        if not event_class_match:
            return False

        resource_class_match = not self.resource_classes or \
            any(isinstance(event.resource, cls) for cls in self.resource_classes)
        if not resource_class_match:
            return False

        return not self.resource_ids or event.resource.id in self.resource_ids
