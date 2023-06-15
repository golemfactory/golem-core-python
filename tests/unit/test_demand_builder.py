from dataclasses import dataclass

import pytest

from golem_core.core.market_api import (
    DemandBuilder,
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

    mocked_node = mocker.Mock()
    mocked_demand = mocker.patch(
        "golem_core.core.market_api.resources.demand.demand_builder.Demand",
        **{"create_from_properties_constraints": mocker.AsyncMock(return_value="foobar")},
    )

    result = await demand_builder.create_demand(mocked_node)

    assert result == "foobar"

    mocked_demand.create_from_properties_constraints.assert_called_with(
        mocked_node,
        demand_builder.properties,
        demand_builder.constraints,
    )
