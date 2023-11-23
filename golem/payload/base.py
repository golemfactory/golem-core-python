import abc
import dataclasses
import enum
from typing import Any, Dict, Final, List, Tuple, Type, TypeVar

from golem.payload.constraints import Constraint, ConstraintOperator, Constraints
from golem.payload.exceptions import InvalidProperties
from golem.payload.properties import Properties

TPayload = TypeVar("TPayload", bound="Payload")

PROP_KEY: Final[str] = "key"
PROP_OPERATOR: Final[str] = "operator"
PROP_MODEL_FIELD_TYPE: Final[str] = "model_field_type"


class PayloadFieldType(enum.Enum):
    constraint = "constraint"
    property = "property"


@dataclasses.dataclass
class Payload(abc.ABC):
    r"""Base class for convenient declaration of Golem's property and constraints syntax.

    Provides helper methods to translate fields between python class and Golem's property and
    constraints syntax.

    Base class for descriptions of the payload required by the requestor.

    example usage::

        import asyncio

        from dataclasses import dataclass
        from golem.resources.market import DemandBuilder, prop, constraint, Payload, RUNTIME_NAME, INF_MEM, INF_STORAGE

        CUSTOM_RUNTIME_NAME = "my-runtime"
        CUSTOM_PROPERTY = "golem.srv.app.myprop"


        @dataclass
        class MyPayload(Payload):
            myprop: str = prop(CUSTOM_PROPERTY, default="myvalue")
            runtime: str = constraint(RUNTIME_NAME, default=CUSTOM_RUNTIME_NAME)
            min_mem_gib: float = constraint(INF_MEM, ">=", default=16)
            min_storage_gib: float = constraint(INF_STORAGE, ">=", default=1024)


        async def main():
            builder = DemandBuilder()
            payload = MyPayload(myprop="othervalue", min_mem_gib=32)
            await builder.add(payload)
            print(builder)

        asyncio.run(main())

    output::

        {'properties': {'golem.srv.app.myprop': 'othervalue'}, 'constraints': ['(&(golem.runtime.name=my-runtime)\n\t(golem.inf.mem.gib>=32)\n\t(golem.inf.storage.gib>=1024))']}



    """  # noqa

    def __init__(self, **kwargs):  # pragma: no cover
        pass

    async def build_properties_and_constraints(self) -> Tuple[Properties, Constraints]:
        return self._build_properties(), self._build_constraints()

    def _build_properties(self) -> Properties:
        """Return a collection of properties declared in the model."""
        return Properties(
            {
                field.metadata[PROP_KEY]: getattr(self, field.name)
                for field in self._get_fields(PayloadFieldType.property)
            }
        )

    def _build_constraints(self) -> Constraints:
        """Return a serialized collection of constraint values."""
        return Constraints(
            [
                Constraint(
                    property_name=field.metadata[PROP_KEY],
                    operator=field.metadata[PROP_OPERATOR],
                    value=getattr(self, field.name),
                )
                for field in self._get_fields(PayloadFieldType.constraint)
            ]
        )

    @classmethod
    def _get_fields(cls, field_type: PayloadFieldType) -> List[dataclasses.Field]:
        """Return a list of fields based on given type."""
        return [
            f
            for f in dataclasses.fields(cls)
            if PROP_KEY in f.metadata and f.metadata.get(PROP_MODEL_FIELD_TYPE) == field_type
        ]

    @classmethod
    def from_properties(cls: Type[TPayload], props: Dict[str, Any]) -> TPayload:
        """Initialize the model with properties from given dictionary.

        Only properties defined in model will be picked up from given dictionary, ignoring other
        keys. In this way several models can be initialized from the same dictionary and all models
        will only load their own data.
        """
        field_map = {
            field.metadata[PROP_KEY]: field for field in cls._get_fields(PayloadFieldType.property)
        }
        data = {
            field_map[key].name: Properties._deserialize_value(val, field_map[key])
            for (key, val) in props.items()
            if key in field_map
        }
        try:
            return cls(**data)
        except TypeError as e:
            raise InvalidProperties(f"Missing key: {e}") from e
        except Exception as e:
            raise InvalidProperties(str(e)) from e


def prop(
    key: str,
    *,
    default: Any = dataclasses.MISSING,
    default_factory: Any = dataclasses.MISSING,
    init: bool = True,
):
    """
    Return a property-type dataclass field for a Payload.

    :param key: the key of the property, e.g. "golem.runtime.name"
    :param default: the default value of the property
    :param default_factory: the default value factory for the property

    example:
    ```python
    >>> from dataclasses import dataclass
    >>> from golem.resources.market import Payload, prop, DemandBuilder
    >>>
    >>> @dataclass
    ... class Foo(Payload):
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
        metadata={PROP_KEY: key, PROP_MODEL_FIELD_TYPE: PayloadFieldType.property},
        init=init,
    )


def constraint(
    key: str,
    operator: ConstraintOperator = "=",
    *,
    default: Any = dataclasses.MISSING,
    default_factory: Any = dataclasses.MISSING,
    init: bool = True,
):
    """Return a constraint-type dataclass field for a Payload.

    :param key: the key of the property on which the constraint is made - e.g.
        "golem.srv.comp.task_package"
    :param operator: constraint's operator, one of: "=", ">=", "<="
    :param default: the default value for the constraint
    :param default_factory: the default value factory for the constraint

    example:
    ```python
    >>> from dataclasses import dataclass
    >>> from golem.resources.market import Payload, constraint, DemandBuilder
    >>>
    >>> @dataclass
    ... class Foo(Payload):
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
            PROP_MODEL_FIELD_TYPE: PayloadFieldType.constraint,
        },
        init=init,
    )
