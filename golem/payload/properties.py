from copy import deepcopy
from typing import Any, Dict

from golem.payload.mixins import PropsConsSerializerMixin

_missing = object()


class Properties(PropsConsSerializerMixin, dict):
    """Low level wrapper class for Golem's Market API properties manipulation."""

    def __init__(self, mapping=_missing, /) -> None:
        if mapping is _missing:
            super().__init__()
            return

        mapping_deep_copy = deepcopy(mapping)

        super().__init__(mapping_deep_copy)

    def serialize(self) -> Dict[str, Any]:
        """Serialize complex objects into format handled by Market API properties specification."""
        return {
            key: self._serialize_property(value) for key, value in self.items() if value is not None
        }

    def _serialize_property(self, value: Any) -> Any:
        return self._serialize_value(value)
