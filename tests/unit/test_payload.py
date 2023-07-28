import datetime
from dataclasses import Field, dataclass, fields
from enum import Enum
from typing import Dict, Optional

import pytest

from golem.payload import (
    Constraint,
    Constraints,
    InvalidProperties,
    Payload,
    Properties,
    constraint,
    prop,
)


class ExampleEnum(Enum):
    ONE = "one"
    TWO = "two"


@dataclass
class Foo(Payload):
    bar: str = prop("bar.dotted.path", default="cafebiba")
    max_baz: int = constraint("baz", "<=", default=100)
    min_baz: int = constraint("baz", ">=", default=1)
    lst: list = constraint("lst", "=", default_factory=list)


@dataclass
class FooToo(Payload):
    text: str = prop("some.path")
    baz: int = constraint("baz", "=", default=21)
    en: ExampleEnum = prop("some_enum", default=ExampleEnum.TWO)
    en_optional: Optional[ExampleEnum] = prop("some_op_enum", default=ExampleEnum.TWO)
    created_at: datetime.datetime = prop("created_at", default_factory=datetime.datetime.now)
    updated_at: Optional[datetime.datetime] = prop("updated_at", default=None)

    def __post_init__(self):
        if self.text == "blow up please!":
            raise ValueError("Some validation error!")


FooTooFields: Dict[str, Field] = {f.name: f for f in fields(FooToo)}


@dataclass
class FooZero(Payload):
    pass


@pytest.mark.parametrize(
    "model, expected_properties, expected_constraints",
    (
        (
            Foo(),
            Properties({"bar.dotted.path": "cafebiba"}),
            Constraints(
                [
                    Constraint("baz", "<=", 100),
                    Constraint("baz", ">=", 1),
                    Constraint("lst", "=", []),
                ]
            ),
        ),
        (
            Foo(bar="bar", min_baz=54, max_baz=200),
            Properties({"bar.dotted.path": "bar"}),
            Constraints(
                [
                    Constraint("baz", "<=", 200),
                    Constraint("baz", ">=", 54),
                    Constraint("lst", "=", []),
                ]
            ),
        ),
        (
            Foo(lst=["some", 1, "value", 2]),
            Properties({"bar.dotted.path": "cafebiba"}),
            Constraints(
                [
                    Constraint("baz", "<=", 100),
                    Constraint("baz", ">=", 1),
                    Constraint("lst", "=", ["some", 1, "value", 2]),
                ]
            ),
        ),
    ),
)
async def test_serialize(model, expected_properties, expected_constraints):
    properties, constraints = await model.build_properties_and_constraints()

    assert properties == expected_properties
    assert constraints == expected_constraints


def test_from_properties():
    model = FooToo.from_properties(
        {
            "some.path": "some text",
            "some_enum": "one",
            "some_op_enum": "one",
            "created_at": 1680785690000,
            "updated_at": 1680785690000,
            "extra_field": "should_be_ignored",
        }
    )

    assert model == FooToo(
        text="some text",
        en=ExampleEnum.ONE,
        en_optional=ExampleEnum.ONE,
        created_at=datetime.datetime(2023, 4, 6, 12, 54, 50, tzinfo=datetime.timezone.utc),
        updated_at=datetime.datetime(2023, 4, 6, 12, 54, 50, tzinfo=datetime.timezone.utc),
    )


def test_from_properties_missing_key():
    with pytest.raises(InvalidProperties, match="Missing key"):
        FooToo.from_properties(
            {
                "some_enum": "one",
                "created_at": 1680785690000,
                "extra_field": "should_be_ignored",
            }
        )


def test_from_properties_custom_validation():
    with pytest.raises(InvalidProperties, match="validation error"):
        FooToo.from_properties(
            {
                "some.path": "blow up please!",
                "some_enum": "one",
                "created_at": 1680785690000,
                "extra_field": "should_be_ignored",
            }
        )
