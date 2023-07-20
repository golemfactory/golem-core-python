import datetime
import enum
import inspect
from dataclasses import Field
from typing import Any

from golem.utils.typing import match_type_union_aware


class PropsConsSerializerMixin:
    @classmethod
    def _serialize_value(cls, value: Any) -> Any:
        """Return value in primitive format compatible with Golem's property \
        and constraint syntax."""

        if isinstance(value, (list, tuple)):
            return type(value)(cls._serialize_value(v) for v in value)

        if isinstance(value, datetime.datetime):
            return int(value.replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)

        if isinstance(value, enum.Enum):
            return value.value

        return value

    @classmethod
    def _deserialize_value(cls, value: Any, field: Field) -> Any:
        """Return proper value for field from given primitive.

        Intended to be overriden with additional type serialisation methods.
        """
        if matched_type := match_type_union_aware(
            field.type, lambda t: inspect.isclass(t) and issubclass(t, datetime.datetime)
        ):
            return matched_type.fromtimestamp(int(float(value) * 0.001), datetime.timezone.utc)

        if matched_type := match_type_union_aware(
            field.type, lambda t: inspect.isclass(t) and issubclass(t, enum.Enum)
        ):
            return matched_type(value)

        return value
