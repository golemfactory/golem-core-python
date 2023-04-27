import abc
import dataclasses
import datetime
import enum
import inspect
from typing import Any, Dict, Final, Iterable, List, Literal, Tuple, Type, TypeVar

from golem_core.core.market_api.resources.demand.demand_offer_base.exceptions import (
    ConstraintException,
    InvalidPropertiesError,
)
from golem_core.utils.typing import match_type_union_aware

TDemandOfferBaseModel = TypeVar("TDemandOfferBaseModel", bound="DemandOfferBaseModel")

PROP_KEY: Final[str] = "key"
PROP_OPERATOR: Final[str] = "operator"
PROP_MODEL_FIELD_TYPE: Final[str] = "model_field_type"

ConstraintOperator = Literal["=", ">=", "<="]
ConstraintGroupOperator = Literal["&", "|", "!"]


class DemandOfferBaseModelFieldType(enum.Enum):
    constraint = "constraint"
    property = "property"


@dataclasses.dataclass
class DemandOfferBaseModel(abc.ABC):
    """Base class for convenient declaration of Golem's property and constraints syntax.

    Provides helper methods to translate fields between python class and Golem's property and
    constraints syntax.
    """

    def __init__(self, **kwargs):  # pragma: no cover
        pass

    async def serialize(self) -> Tuple[Dict[str, Any], str]:
        """Return a tuple of serialized properties and constraints.

        Intended to be overriden with additional logic that requires async context.
        """
        return self._serialize_properties(), self._serialize_constraints()

    def _serialize_properties(self) -> Dict[str, Any]:
        """Return a serialized collection of property values."""
        return {
            field.metadata[PROP_KEY]: self._serialize_property(getattr(self, field.name), field)
            for field in self._get_fields(DemandOfferBaseModelFieldType.property)
            if getattr(self, field.name) is not None
        }

    def _serialize_constraints(self) -> str:
        """Return a serialized collection of constraint values."""
        return join_str_constraints(
            self._serialize_constraint(getattr(self, field.name), field)
            for field in self._get_fields(DemandOfferBaseModelFieldType.constraint)
            if getattr(self, field.name) is not None
        )

    @classmethod
    def _serialize_property(cls, value: Any, field: dataclasses.Field) -> Any:
        """Return serialized property value."""
        return cls.serialize_value(value)

    @classmethod
    def _serialize_constraint(cls, value: Any, field: dataclasses.Field) -> str:
        """Return serialized constraint value."""
        if isinstance(value, (list, tuple)):
            if value:
                return join_str_constraints([cls._serialize_constraint(v, field) for v in value])

            return ""

        serialized_value = cls.serialize_value(value)

        return "({key}{operator}{value})".format(
            key=field.metadata[PROP_KEY],
            operator=field.metadata[PROP_OPERATOR],
            value=serialized_value,
        )

    @classmethod
    def serialize_value(cls, value: Any) -> Any:
        """Return value in primitive format compatible with Golem's property and constraint syntax.

        Intended to be overriden with additional type serialisation methods.
        """

        if isinstance(value, (list, tuple)):
            return type(value)(cls.serialize_value(v) for v in value)

        if isinstance(value, datetime.datetime):
            return int(value.timestamp() * 1000)

        if isinstance(value, enum.Enum):
            return value.value

        return value

    @classmethod
    def deserialize_value(cls, value: Any, field: dataclasses.Field) -> Any:
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

    @classmethod
    def _get_fields(cls, field_type: DemandOfferBaseModelFieldType) -> List[dataclasses.Field]:
        """Return a list of fields based on given type."""
        return [
            f
            for f in dataclasses.fields(cls)
            if PROP_KEY in f.metadata and f.metadata.get(PROP_MODEL_FIELD_TYPE) == field_type
        ]

    @classmethod
    def from_properties(
        cls: Type[TDemandOfferBaseModel], props: Dict[str, Any]
    ) -> TDemandOfferBaseModel:
        """Initialize the model with properties from given dictionary.

        Only properties defined in model will be picked up from given dictionary, ignoring other
        keys. In this way several models can be initialized from the same dictionary and all models
        will only load their own data.
        """
        field_map = {
            field.metadata[PROP_KEY]: field
            for field in cls._get_fields(DemandOfferBaseModelFieldType.property)
        }
        data = {
            field_map[key].name: cls.deserialize_value(val, field_map[key])
            for (key, val) in props.items()
            if key in field_map
        }
        try:
            return cls(**data)
        except TypeError as e:
            raise InvalidPropertiesError(f"Missing key: {e}") from e
        except Exception as e:
            raise InvalidPropertiesError(str(e)) from e


def prop(
    key: str, *, default: Any = dataclasses.MISSING, default_factory: Any = dataclasses.MISSING
):
    """
    Return a property-type dataclass field for a DemandOfferBaseModel.

    :param key: the key of the property, e.g. "golem.runtime.name"
    :param default: the default value of the property
    :param default_factory: the default value factory for the property

    example:
    ```python
    >>> from dataclasses import dataclass
    >>> from golem_core.core.market_api import DemandOfferBaseModel, prop, DemandBuilder
    >>>
    >>> @dataclass
    ... class Foo(DemandOfferBaseModel):
    ...     bar: int = prop("bar", default=100)
    ...
    >>> builder = DemandBuilder()
    >>> await builder.add(Foo(bar=42))
    >>> print(builder.properties)
    {'bar': 42}
    ```
    """
    return dataclasses.field(  # type: ignore[call-overload]
        default=default,
        default_factory=default_factory,
        metadata={PROP_KEY: key, PROP_MODEL_FIELD_TYPE: DemandOfferBaseModelFieldType.property},
    )


def constraint(
    key: str,
    operator: ConstraintOperator = "=",
    *,
    default: Any = dataclasses.MISSING,
    default_factory: Any = dataclasses.MISSING,
):
    """Return a constraint-type dataclass field for a DemandOfferBaseModel.

    :param key: the key of the property on which the constraint is made - e.g.
        "golem.srv.comp.task_package"
    :param operator: constraint's operator, one of: "=", ">=", "<="
    :param default: the default value for the constraint
    :param default_factory: the default value factory for the constraint

    example:
    ```python
    >>> from dataclasses import dataclass
    >>> from golem_core.core.market_api import DemandOfferBaseModel, constraint, DemandBuilder
    >>>
    >>> @dataclass
    ... class Foo(DemandOfferBaseModel):
    ...     max_baz: int = constraint("baz", "<=", default=100)
    ...
    >>> builder = DemandBuilder()
    >>> await builder.add(Foo(max_baz=42))
    >>> print(builder.constraints)
    '(baz<=42)'
    ```
    """
    return dataclasses.field(  # type: ignore[call-overload]
        default=default,
        default_factory=default_factory,
        metadata={
            PROP_KEY: key,
            PROP_OPERATOR: operator,
            PROP_MODEL_FIELD_TYPE: DemandOfferBaseModelFieldType.constraint,
        },
    )


def join_str_constraints(
    constraints: Iterable[str], operator: ConstraintGroupOperator = "&"
) -> str:
    """Join a list of constraints using the given opererator.

    The semantics here reflect LDAP filters: https://ldap.com/ldap-filters/

    :param constraints: list of strings representing individual constraints
                        (which may include previously joined constraint groups)
    :param operator: constraint group operator, one of "&", "|", "!", which represent
                     "and", "or" and "not" operations on those constraints.
                     "!" requires that the list contains one and only one constraint.
                     Defaults to "&" (and) if not given.
    :return: string representation of the compound constraint.

    example:
    ```python
    >>> from dataclasses import dataclass
    >>> from golem_core.core.market_api import join_str_constraints
    >>>
    >>> min_bar = '(bar>=42)'
    >>> max_bar = '(bar<=128)'
    >>> print(join_str_constraints([min_bar, max_bar]))
    (&(bar>=42)
        (bar<=128))
    ```
    """
    constraints = [c for c in constraints if c]

    if operator == "!":
        if len(constraints) == 1:
            return f"({operator}{constraints[0]})"
        else:
            raise ConstraintException(f"{operator} requires exactly one component.")

    if not constraints:
        return f"({operator})"

    if len(constraints) == 1:
        return f"{constraints[0]}"

    rules = "\n\t".join(constraints)
    return f"({operator}{rules})"


__all__ = (
    "DemandOfferBaseModel",
    "prop",
    "constraint",
    "join_str_constraints",
)
