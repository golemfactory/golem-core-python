from dataclasses import dataclass

import pytest

from golem_core.core.market_api import (
    DemandBuilder,
    DemandBuilderDecorator,
    DemandOfferBaseModel,
    constraint,
    prop,
)


@dataclass
class ExampleModel(DemandOfferBaseModel):
    prop1: int = prop("some.prop1.path")
    prop2: int = prop("some.prop2.path")
    con1: int = constraint("some.con1.path", "=")
    con2: int = constraint("some.con2.path", "<=")


class ExampleBuilderDecorator(DemandBuilderDecorator):
    async def decorate_demand_builder(self, demand_builder: DemandBuilder) -> None:
        demand_builder.add_properties({"some.fancy.field": "was just added by demand decorator"})


class AnotherExampleBuilderDecorator(DemandBuilderDecorator):
    async def decorate_demand_builder(self, demand_builder: DemandBuilder) -> None:
        demand_builder.add_constraints("field=added")


@pytest.mark.asyncio
async def test_add():
    model = ExampleModel(prop1=1, prop2=2, con1=3, con2=4)

    demand_builder = DemandBuilder()

    await demand_builder.add(model)

    assert demand_builder.properties == {
        "some.prop1.path": 1,
        "some.prop2.path": 2,
    }

    assert demand_builder.constraints == "(&(some.con1.path=3)\n\t(some.con2.path<=4))"


def test_repr():
    assert str(DemandBuilder()) == "{'properties': {}, 'constraints': []}"


@pytest.mark.asyncio
async def test_create_demand(mocker):
    demand_builder = DemandBuilder()

    allocation = mocker.Mock()
    mocked_instance = mocker.Mock(
        allocations=[allocation]
    )  # FIXME: allocations should be not included this way
    mocked_node = mocker.Mock()
    mocked_demand = mocker.patch(
        "golem_core.core.market_api.resources.demand.demand_builder.Demand",
        **{"create_from_properties_constraints": mocker.AsyncMock(return_value=mocked_instance)},
    )

    result = await demand_builder.create_demand(mocked_node, [allocation])

    assert result == mocked_instance

    mocked_demand.create_from_properties_constraints.assert_called_with(
        mocked_node, demand_builder.properties, demand_builder.constraints, [allocation]
    )


@pytest.mark.asyncio
async def test_decorate():
    demand_builder = DemandBuilder()

    assert demand_builder.properties == {}
    assert demand_builder.constraints == "(&)"

    await demand_builder.decorate(ExampleBuilderDecorator(), AnotherExampleBuilderDecorator())

    assert demand_builder.properties == {
        "some.fancy.field": "was just added by demand decorator",
    }

    assert demand_builder.constraints == "field=added"
