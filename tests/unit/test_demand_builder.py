import datetime
from enum import Enum
from typing import Dict

import pytest
from dataclasses import dataclass, fields, Field

from golem_core.demand_builder.model import (
    Model,
    prop,
    constraint,
    InvalidPropertiesError,
    join_str_constraints,
    ConstraintException,
)


class ExampleEnum(Enum):
    ONE = 'one'
    TWO = 'two'

@dataclass
class Foo(Model):
    bar: str = prop("bar.dotted.path", "cafebiba")
    max_baz: int = constraint("baz", "<=", 100)
    min_baz: int = constraint("baz", ">=", 1)
    lst: list = constraint("lst", "=", default_factory=list)


@dataclass
class FooToo(Model):
    text: str = prop("some.path")
    baz: int = constraint("baz", "=", 21)
    en: ExampleEnum = prop("some_enum", ExampleEnum.TWO)
    created_at: datetime.datetime = prop("created_at", default_factory=datetime.datetime.now)

    def __post_init__(self):
        if self.text == 'blow up please!':
            raise ValueError('Some validation error!')


FooTooFields: Dict[str, Field] = {f.name: f for f in fields(FooToo)}

@dataclass
class FooZero(Model):
    pass


@pytest.mark.parametrize(
    "model, expected_properties, expected_constraints",
    (
        (
            Foo(),
            {"bar.dotted.path": "cafebiba"},
            "(&(baz<=100)\n\t(baz>=1))",
        ),
        (
            Foo(bar="bar", min_baz=54, max_baz=200),
            {"bar.dotted.path": "bar"},
            "(&(baz<=200)\n\t(baz>=54))",
        ),
        (
            Foo(lst=["some", 1, "value", 2]),
            {"bar.dotted.path": "cafebiba"},
            "(&(baz<=100)\n\t(baz>=1)\n\t(&(lst=some)\n\t(lst=1)\n\t(lst=value)\n\t(lst=2)))",
        ),
    ),
)
@pytest.mark.asyncio
async def test_serialize(model, expected_properties, expected_constraints):
    properties, constraints = await model.serialize()

    assert properties == expected_properties
    assert constraints == expected_constraints

@pytest.mark.parametrize(
    'value, expected',
    (
        (
            [1, 2, 3],
            [1, 2, 3],
        ),
        (
            (1, 2, 3),
            (1, 2, 3),
        ),
        (
            datetime.datetime(2023, 4, 6, 12, 54, 50, tzinfo=datetime.timezone.utc),
            1680785690000,
        ),
        (
            ExampleEnum.ONE,
            "one"
        ),
        (
            [[1, 2], (ExampleEnum.ONE, ExampleEnum.TWO), datetime.datetime(2023, 4, 6, 12, 54, 50, tzinfo=datetime.timezone.utc)],
            [[1, 2], ("one", "two"), 1680785690000]
        )
    )
)
def test_serialize_value(value, expected):
    assert Model.serialize_value(value) == expected

@pytest.mark.parametrize(
    'value, field, expected',
    (
        (
            123,
            FooTooFields['baz'],
            123,
        ),
        (
            "one",
            FooTooFields['en'],
            ExampleEnum.ONE,
        ),
        (
            1680785690000,
            FooTooFields['created_at'],
            datetime.datetime(2023, 4, 6, 12, 54, 50, tzinfo=datetime.timezone.utc)
        )
    )
)
def test_deserialize_value(value, field, expected):
    assert Model.deserialize_value(value, field) == expected


def test_from_properties():
    model = FooToo.from_properties({
        'some.path': 'some text',
        'some_enum': 'one',
        'created_at': 1680785690000,
        'extra_field': 'should_be_ignored',
    })

    assert model == FooToo(
        text='some text',
        en=ExampleEnum.ONE,
        created_at=datetime.datetime(2023, 4, 6, 12, 54, 50, tzinfo=datetime.timezone.utc),
    )

def test_from_properties_missing_key():
    with pytest.raises(InvalidPropertiesError, match='Missing key'):
        FooToo.from_properties({
            'some_enum': 'one',
            'created_at': 1680785690000,
            'extra_field': 'should_be_ignored',
        })

def test_from_properties_custom_validation():
    with pytest.raises(InvalidPropertiesError, match='validation error'):
        FooToo.from_properties({
            'some.path': 'blow up please!',
            'some_enum': 'one',
            'created_at': 1680785690000,
            'extra_field': 'should_be_ignored',
        })


@pytest.mark.parametrize(
    'items, operator, expected',
    (
        (
            ['A', 'B', 'C'],
            '&',
            '(&A\n\tB\n\tC)',
        ),
        (
            ['A', 'B', 'C'],
            '|',
            '(|A\n\tB\n\tC)',
        ),
        (
            ['A',],
            '!',
            '(!A)',
        ),
        (
            [],
            '&',
            '(&)',
        ),
        (
            ['A'],
            '&',
            'A',
        ),
    )
)
def test_join_str_constraints(items, operator, expected):
    assert join_str_constraints(items, operator) == expected


def test_join_str_constraints_negation_with_multiple_constraints():
    with pytest.raises(ConstraintException):
        join_str_constraints(['A', 'B', 'C'], '!')
