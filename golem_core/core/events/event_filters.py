from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Tuple, Type

from golem_core.core.events import Event

######################################
#   GENERAL NOTE ABOUT EVENT FILTERS
#
#   Thanks to the EventFilters, event listeners listening for the same
#   sort of events are kept together. Purpose:
#   *   A little more efficient (less checks to execute on an single event)
#   *   We might want to implement one day some  "this will never happen" logic
#       - e.g. after we deleted a resource, it will never change again. This will not be
#       possible with unstructured callables.
#
#   BUT: this might end up useless - but cleanup will be very easy, as this is internal to the EventBus.
class EventFilter(ABC):
    """Base class for all EventFilters"""
    @abstractmethod
    def includes(self, event: Event) -> bool:
        raise NotImplemented


@dataclass(frozen=True)
class AnyEventFilter(EventFilter):
    """Selection based on the Event classes."""
    event_classes: Tuple[Type[Event], ...]

    def includes(self, event: Event) -> bool:
        return not self.event_classes or any(isinstance(event, cls) for cls in self.event_classes)

