from abc import ABC
from typing import TypeVar

TEvent = TypeVar("TEvent", bound="Event")

class Event(ABC):
    """Base class for all events."""
