import abc
import inspect
import json
import enum
import dataclasses
import datetime

from typing import Any, Dict, List, Type, TypeVar, Union, Final, get_origin, get_args, Literal


TModel = TypeVar("TModel", bound="Model")
Props = Dict[str, str]

PROP_KEY: Final[str] = "key"
PROP_OPERATOR: Final[str] = "operator"
PROP_MODEL_FIELD_TYPE: Final[str] = "model_field_type"

ConstraintOperator = Literal["=", ">=", "<="]
ConstraintGroupOperator = Literal["&", "|", "!"]


@dataclasses.dataclass(frozen=True)
class _PyField:
    name: str
    type: type
    required: bool

    def encode(self, value: str) -> Any:
        if get_origin(self.type) == Union:
            if datetime in get_args(self.type):
                # TODO: fix this.
                return datetime.datetime.fromtimestamp(int(float(value) * 0.001), datetime.timezone.utc)

            return value

        if inspect.isclass(self.type) and issubclass(self.type, enum.Enum):
            return self.type(value)

        return value


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

    def __init__(self, **kwargs):
        pass

    def serialize_properties(self) -> Dict[str, Any]:
        """Return a serialized collection of property values."""
        return {
            field.metadata[PROP_KEY]: self._serialize_value(getattr(self, field.name))
            for field in self._get_fields(ModelFieldType.property)
            if getattr(self, field.name) is not None
        }

    def serialize_constraints(self) -> str:
        """Return a serialized collection of constraint values."""
        serialized = []

        for field in self._get_fields(ModelFieldType.constraint):
            value = getattr(self, field.name)
            if value is None:
                continue

            serialized.append(
                "({key}{operator}{value})".format(
                    key=field.metadata[PROP_KEY],
                    operator=field.metadata[PROP_OPERATOR],
                    value=self._serialize_value(value)
                )
            )

        return join_str_constraints(serialized)

    @classmethod
    def _serialize_value(cls, value: Any) -> Any:
        """Return value in format compatible with Demand"""

        if isinstance(value, (list, tuple)):
            return type(value)(cls._serialize_value(v) for v in value)

        if isinstance(value, datetime.datetime):
            return int(value.timestamp() * 1000)

        if isinstance(value, enum.Enum):
            return value.value

        assert isinstance(value, (str, int, float)), f"Serializing \"{type(value)}\" is not supported!"

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
            f.metadata[PROP_KEY]: _PyField(
                name=f.name,
                type=f.type,
                required=f.default is dataclasses.MISSING
            )
            for f in cls._property_fields()
        }
        data = {
            field_map[key].name: field_map[key].encode(val)
            for (key, val) in props.items()
            if key in field_map
        }
        try:
            cls._custom_mapping(props, data)
            return cls(**data)
        except KeyError as exc:
            raise InvalidPropertiesError(f"Missing key: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise InvalidPropertiesError(f"Error when decoding '{exc.doc}': {exc}") from exc
        except Exception as exc:
            raise InvalidPropertiesError() from exc


def constraint(
    key: str, operator: ConstraintOperator = "=", default=dataclasses.MISSING, default_factory=dataclasses.MISSING
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
    >>> from yapapi.props.base import Model, constraint, constraint_model_serialize
    >>>
    >>> @dataclass
    ... class Foo(Model):
    ...     max_baz: int = constraint("baz", "<=", 100)
    ...
    >>> constraints = constraint_model_serialize(Foo())
    >>> print(constraints)
    ['(baz<=100)']
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


def prop(key: str, default=dataclasses.MISSING, default_factory=dataclasses.MISSING):
    """
    Return a property-type dataclass field for a Model.

    :param key: the key of the property, e.g. "golem.runtime.name"
    :param default: the default value of the property

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
    >>> builder.add(Foo(bar=42))
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


def constraint_to_str(value, field: dataclasses.Field) -> str:
    """Get string representation of a constraint with a given value.

    :param value: the value of the the constraint field
    :param field: the dataclass field for this constraint
    """
    if isinstance(value, List):
        return join_str_constraints([constraint_to_str(v, field) for v in value]) if value else ""
    else:
        return f"({field.metadata[PROP_KEY]}{field.metadata[PROP_OPERATOR]}{value})"


def constraint_model_serialize(m: Model) -> List[str]:
    """
    Return a list of stringified constraints on the given Model instance.

    :param m: instance of Model for which we want the constraints serialized
    """
    return [
        constraint_to_str(getattr(m, f.name), f)
        for f in dataclasses.fields(type(m))
        if f.metadata.get(PROP_MODEL_FIELD_TYPE, "") == ModelFieldType.constraint
    ]


def join_str_constraints(constraints: List[str], operator: ConstraintGroupOperator = "&") -> str:
    """
    Join a list of constraints using the given opererator.

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
    >>> from yapapi.props.base import (
    >>>     Model, constraint, constraint_model_serialize, join_str_constraints
    >>> )
    >>>
    >>> @dataclass
    ... class Foo(Model):
    ...     min_bar: int = constraint("bar", ">=", 42)
    ...     max_bar: int = constraint("bar", "<=", 128)
    ...
    >>> print(join_str_constraints(constraint_model_serialize(Foo())))
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
    "constraint",
    "prop",
    "constraint_to_str",
    "constraint_model_serialize",
    "join_str_constraints",
)
