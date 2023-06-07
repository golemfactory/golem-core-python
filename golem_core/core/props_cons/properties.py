from copy import deepcopy
from typing import Any, Mapping

from golem_core.core.props_cons.base import PropsConstrsSerializer


class Properties(PropsConstrsSerializer, dict):
    """Low level wrapper class for Golem's Market API properties manipulation."""

    def __init__(self, mapping, /) -> None:
        mapping_deep_copy = deepcopy(mapping)
        super(mapping_deep_copy)

    def serialize(self) -> Mapping[str, Any]:
        """Serialize complex objects into format handled by Market API properties specification."""
        return {key: self._serialize_property(value) for key, value in self.items()}

    def _serialize_property(self, value: Any) -> Any:
        return self._serialize_value(value)
