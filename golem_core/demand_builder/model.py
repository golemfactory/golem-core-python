import abc
import inspect
import enum
import dataclasses
import datetime

from typing import (
    Any,
    Dict,
    List,
    Type,
    TypeVar,
    Union,
    Final,
    get_origin,
    get_args,
    Literal,
    Tuple,
    Iterable,
)

TModel = TypeVar("TModel", bound="Model")
Props = Dict[str, str]

PROP_KEY: Final[str] = "key"
PROP_OPERATOR: Final[str] = "operator"
PROP_MODEL_FIELD_TYPE: Final[str] = "model_field_type"

ConstraintOperator = Literal["=", ">=", "<="]
ConstraintGroupOperator = Literal["&", "|", "!"]


class ConstraintException(Exception):
    pass


class InvalidPropertiesError(Exception):
    """Raised by `Model.from_properties(cls, properties)` when given invalid `properties`."""


class ModelFieldType(enum.Enum):
    constraint = "constraint"
    property = "property"


@dataclasses.dataclass
class Model(abc.ABC):
    """
    Base class from which all property models inherit.

    Provides helper methods to load the property model data from a dictionary and
    to get a mapping of all the keys available in the given model.
    """

    def __init__(self, **kwargs):  # pragma: no cover
        pass

    async def serialize(self) -> Tuple[Dict[str, Any], str]:
        """Return a tuple of serialized model properties and constraints.

        Intended to be overriden with additional logic that requires async context.
        """
        return self._serialize_properties(), self._serialize_constraints()

    def _serialize_properties(self) -> Dict[str, Any]:
        """Return a serialized collection of property values."""
        return {
            field.metadata[PROP_KEY]: self._serialize_property(getattr(self, field.name), field)
            for field in self._get_fields(ModelFieldType.property)
            if getattr(self, field.name) is not None
        }

    def _serialize_constraints(self) -> str:
        """Return a serialized collection of constraint values."""
        return join_str_constraints(
            self._serialize_constraint(getattr(self, field.name), field)
            for field in self._get_fields(ModelFieldType.constraint)
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
        """Return value in primitive format compatible with Demand.

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
        if inspect.isclass(field.type) and issubclass(field.type, datetime.datetime):
            return datetime.datetime.fromtimestamp(
                int(float(value) * 0.001),
                datetime.timezone.utc
            )

        if inspect.isclass(field.type) and issubclass(field.type, enum.Enum):
            return field.type(value)

        return value

    @classmethod
    def _get_fields(cls, field_type: ModelFieldType) -> List[dataclasses.Field]:
        """Return a list of Demand fields based on given type."""
        return [
            f
            for f in dataclasses.fields(cls)
            if PROP_KEY in f.metadata
            and f.metadata.get(PROP_MODEL_FIELD_TYPE) == field_type
        ]

    @classmethod
    def from_properties(cls: Type[TModel], props: Props) -> TModel:
        """
        Initialize the model from a dictionary representation.

        When provided with a dictionary of properties, it will find the matching keys
        within it and fill the model fields with the values from the dictionary.

        It ignores non-matching keys - i.e. doesn't require filtering of the properties'
        dictionary before the model is fed with the data. Thus, several models can be
        initialized from the same dictionary and all models will only load their own data.
        """
        field_map = {
            field.metadata[PROP_KEY]: field
            for field in cls._get_fields(ModelFieldType.property)
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


def prop(key: str, default: Any = dataclasses.MISSING, default_factory: Any = dataclasses.MISSING):
    """
    Return a property-type dataclass field for a Model.

    :param key: the key of the property, e.g. "golem.runtime.name"
    :param default: the default value of the property
    :param default_factory: the default value factory for the property

    example:
    ```python
    >>> from dataclasses import dataclass
    >>> from yapapi.props.base import Model, prop
    >>> from yapapi.props.builder import DemandBuilder
    >>>
    >>> @dataclass
    ... class Foo(Model):
    ...     bar: int = prop("bar", default=100)
    ...
    >>> builder = DemandBuilder()
    >>> await builder.add(Foo(bar=42))
    >>> print(builder.properties)
    {'bar': 42}
    ```
    """
    return dataclasses.field(  # type: ignore
        default=default,
        default_factory=default_factory,
        metadata={
            PROP_KEY: key,
            PROP_MODEL_FIELD_TYPE: ModelFieldType.property
        },
    )


def constraint(
    key: str,
    operator: ConstraintOperator = "=",
    default: Any = dataclasses.MISSING,
    default_factory: Any = dataclasses.MISSING,
):
    """Return a constraint-type dataclass field for a Model.

    :param key: the key of the property on which the constraint is made - e.g.
        "golem.srv.comp.task_package"
    :param operator: constraint's operator, one of: "=", ">=", "<="
    :param default: the default value for the constraint
    :param default_factory: the default value factory for the constraint

    example:
    ```python
    >>> from dataclasses import dataclass
    >>> from golem_core.demand_builder.model import Model, constraint
    >>> from golem_core.demand_builder.builder import DemandBuilder
    >>>
    >>> @dataclass
    ... class Foo(Model):
    ...     max_baz: int = constraint("baz", "<=", 100)
    ...
    >>> builder = DemandBuilder()
    >>> await builder.add(Foo(max_baz=42))
    >>> print(builder.constraints)
    '(baz<=42)'
    ```
    """
    # the default / default_factory exception is resolved by the `field` function
    return dataclasses.field(  # type: ignore
        default=default,
        default_factory=default_factory,
        metadata={
            PROP_KEY: key,
            PROP_OPERATOR: operator,
            PROP_MODEL_FIELD_TYPE: ModelFieldType.constraint,
        },
    )


def join_str_constraints(
    constraints: Iterable[str],
    operator: ConstraintGroupOperator = "&"
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
    >>> from yapapi.props.base import join_str_constraints
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
    "Model",
    "Props",
    "prop",
    "constraint",
    "join_str_constraints",
    "InvalidPropertiesError",
)
