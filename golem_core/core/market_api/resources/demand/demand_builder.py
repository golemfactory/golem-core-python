import abc
from copy import deepcopy
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from golem_core.core.market_api.resources.demand.demand import Demand
from golem_core.core.market_api.resources.demand.demand_offer_base.model import (
    DemandOfferBaseModel,
    join_str_constraints,
)

if TYPE_CHECKING:  # pragma: no cover
    from golem_core.core.golem_node import GolemNode


class DemandBuilder:
    """Builder that gives ability to collect Demand's properties and constraints in multiple \
    separate steps, prior its creation.

    example usage:

    ```python
    >>> from golem_core.core.market_api import DemandBuilder, pipeline
    >>> from datetime import datetime, timezone
    >>> builder = DemandBuilder()
    >>> await builder.add(defaults.NodeInfo(name="a node", subnet_tag="testnet"))
    >>> await builder.add(defaults.Activity(expiration=datetime.now(timezone.utc)))
    >>> print(builder)
    {'properties':
        {'golem.node.id.name': 'a node',
         'golem.node.debug.subnet': 'testnet',
         'golem.srv.comp.expiration': 1601655628772},
     'constraints': []}
    ```
    """

    def __init__(
        self, properties: Optional[Dict[str, Any]] = None, constraints: Optional[List[str]] = None
    ):
        self._properties: Dict[str, Any] = properties if properties is not None else {}
        self._constraints: List[str] = constraints if constraints is not None else []

    def __repr__(self):
        return repr({"properties": self._properties, "constraints": self._constraints})

    def __eq__(self, other):
        return (
            isinstance(other, DemandBuilder)
            and self._properties == other.properties
            and self.constraints == other.constraints
        )

    @property
    def properties(self) -> Dict:
        """List of properties for this demand."""
        return self._properties

    @property
    def constraints(self) -> str:
        """Constraints definition for this demand."""
        return join_str_constraints(self._constraints)

    async def add(self, model: DemandOfferBaseModel):
        """Add properties and constraints from the given model to this demand definition."""

        properties, constraints = await model.serialize()

        self.add_properties(properties)
        self.add_constraints(constraints)

    def add_properties(self, props: Dict):
        """Add properties from the given dictionary to this demand definition."""
        self._properties.update(props)

    def add_constraints(self, *constraints: str):
        """Add a constraint from given args to the demand definition."""
        self._constraints.extend(constraints)

    async def decorate(self, *decorators: "DemandBuilderDecorator"):
        """Decorate demand definition with given demand decorators."""

        for decorator in decorators:
            await decorator.decorate_demand_builder(self)

    async def create_demand(self, node: "GolemNode") -> "Demand":
        """Create demand and subscribe to its events."""
        return await Demand.create_from_properties_constraints(
            node, self.properties, self.constraints
        )

    @classmethod
    async def from_demand(cls, demand: "Demand") -> "DemandBuilder":
        demand_data = deepcopy(await demand.get_data())

        return cls(demand_data.properties, [demand_data.constraints])


class DemandBuilderDecorator(abc.ABC):
    """An interface that specifies classes that can add properties and constraints through a \
    DemandBuilder."""

    @abc.abstractmethod
    async def decorate_demand_builder(self, demand_builder: DemandBuilder) -> None:
        """Decorate given DemandBuilder.

        Intended to be overriden to customize given DemandBuilder decoration.
        """
