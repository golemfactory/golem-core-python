from dataclasses import dataclass

from golem.payload import (
    Constraint,
    ConstraintGroup,
    Constraints,
    Payload,
    Properties,
    constraint,
    prop,
)
from golem.resources import DemandBuilder


@dataclass
class ExampleModel(Payload):
    prop1: int = prop("some.prop1.path")
    prop2: int = prop("some.prop2.path")
    con1: int = constraint("some.con1.path", "=")
    con2: int = constraint("some.con2.path", "<=")


async def test_add():
    model = ExampleModel(prop1=1, prop2=2, con1=3, con2=4)

    demand_builder = DemandBuilder()

    await demand_builder.add(model)

    assert demand_builder.properties == {
        "some.prop1.path": 1,
        "some.prop2.path": 2,
    }

    assert demand_builder.constraints == Constraints(
        [
            Constraint("some.con1.path", "=", 3),
            Constraint("some.con2.path", "<=", 4),
        ]
    )


def test_add_properties():
    demand_builder = DemandBuilder()

    assert demand_builder.properties.get("foo") != "bar"

    demand_builder.add_properties(
        Properties(
            {
                "foo": "bar",
            }
        )
    )

    assert demand_builder.properties.get("foo") == "bar"

    demand_builder.add_properties(
        Properties(
            {
                "foo": "123",
                "bat": "man",
            }
        )
    )

    assert demand_builder.properties.get("foo") == "123"
    assert demand_builder.properties.get("bat") == "man"


def test_add_constraints():
    demand_builder = DemandBuilder()

    assert demand_builder.constraints == Constraints()

    demand_builder.add_constraints(
        Constraints(
            [
                Constraint("foo", "=", "bar"),
            ]
        )
    )

    assert demand_builder.constraints == Constraints(
        [
            Constraint("foo", "=", "bar"),
        ]
    )

    demand_builder.add_constraints(
        Constraints(
            [
                Constraint("another.field", "<=", "value1"),
                Constraint("collection.to.add", ">=", "value2"),
            ]
        )
    )

    assert demand_builder.constraints == Constraints(
        [
            Constraint("foo", "=", "bar"),
            Constraint("another.field", "<=", "value1"),
            Constraint("collection.to.add", ">=", "value2"),
        ]
    )

    demand_builder.add_constraints(Constraint("single.field", "=", "works too!"))

    assert demand_builder.constraints == Constraints(
        [
            Constraint("foo", "=", "bar"),
            Constraint("another.field", "<=", "value1"),
            Constraint("collection.to.add", ">=", "value2"),
            Constraint("single.field", "=", "works too!"),
        ]
    )

    demand_builder.add_constraints(
        ConstraintGroup([Constraint("field.group", "=", "works too!")], "|")
    )

    assert demand_builder.constraints == Constraints(
        [
            Constraint("foo", "=", "bar"),
            Constraint("another.field", "<=", "value1"),
            Constraint("collection.to.add", ">=", "value2"),
            Constraint("single.field", "=", "works too!"),
            ConstraintGroup([Constraint("field.group", "=", "works too!")], "|"),
        ]
    )


def test_repr():
    assert (
        str(DemandBuilder())
        == "{'properties': {}, 'constraints': Constraints(items=[], operator='&')}"
    )


def test_comparison():
    builder_1 = DemandBuilder(
        Properties(
            {
                "foo": "bar",
            }
        )
    )
    builder_2 = DemandBuilder(
        Properties(
            {
                "foo": "bar",
            }
        )
    )
    builder_3 = DemandBuilder(
        Properties(
            {
                "foo": 123,
            }
        )
    )

    assert builder_1 == builder_2
    assert builder_1 != builder_3


async def test_create_demand(mocker):
    demand_builder = DemandBuilder()

    mocked_node = mocker.Mock()
    mocked_demand = mocker.patch(
        "golem.resources.demand.demand_builder.Demand",
        **{"create_from_properties_constraints": mocker.AsyncMock(return_value="foobar")},
    )

    result = await demand_builder.create_demand(mocked_node)

    assert result == "foobar"

    mocked_demand.create_from_properties_constraints.assert_called_with(
        mocked_node,
        demand_builder.properties,
        demand_builder.constraints,
    )
