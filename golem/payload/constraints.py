from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal, MutableSequence, Union

from golem.payload.mixins import PropsConsSerializerMixin

PropertyName = str
PropertyValue = Any


class ConstraintException(Exception):
    pass


ConstraintOperator = Literal["=", "<=", ">=", "<", ">"]
ConstraintGroupOperator = Literal["&", "|", "!"]


@dataclass
class PayloadSyntaxElement(PropsConsSerializerMixin, ABC):
    def __post_init__(self) -> None:
        self._validate()

    def serialize(self) -> str:
        self._validate()

        return self._serialize()

    @abstractmethod
    def _serialize(self) -> str:
        ...

    def _validate(self) -> None:
        ...


@dataclass
class Constraint(PayloadSyntaxElement):
    property_name: PropertyName
    operator: ConstraintOperator
    value: PropertyValue

    def _serialize(self) -> str:
        serialized_value = self._serialize_value(self.value)

        if not self.value:
            return ""

        if isinstance(self.value, (list, tuple)):
            return ConstraintGroup(
                [Constraint(self.property_name, self.operator, v) for v in serialized_value]
            ).serialize()

        return f"({self.property_name}{self.operator}{serialized_value})"


@dataclass
class ConstraintGroup(PayloadSyntaxElement):
    items: MutableSequence[Union["ConstraintGroup", Constraint]] = field(default_factory=list)
    operator: ConstraintGroupOperator = "&"

    def _validate(self) -> None:
        if self.operator == "!" and 2 <= len(self.items):
            raise ConstraintException("ConstraintGroup with `!` operator can contain only 1 item!")

    def _serialize(self) -> str:
        serialized = [item.serialize() for item in self.items]
        items = "\n\t".join(s for s in serialized if s)

        return f"({self.operator}{items})"


@dataclass
class Constraints(ConstraintGroup):
    pass
