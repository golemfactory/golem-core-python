from copy import deepcopy
from ctypes import Union
from typing import TYPE_CHECKING, Optional

from golem_core.core.market_api.resources.demand.demand import Demand
from golem_core.core.market_api.resources.demand.demand_offer_base.model import DemandOfferBaseModel
from golem_core.core.props_cons.constraints import Constraint, ConstraintGroup, Constraints
from golem_core.core.props_cons.properties import Properties

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
        self, properties: Optional[Properties] = None, constraints: Optional[Constraints] = None
    ):
        self._properties: Properties = properties if properties is not None else Properties()
        self._constraints: Constraints = constraints if constraints is not None else Constraints()

    def __repr__(self):
        return repr({"properties": self._properties, "constraints": self._constraints})

    def __eq__(self, other):
        return (
            isinstance(other, DemandBuilder)
            and self._properties == other.properties
            and self._constraints == other.constraints
        )

    @property
    def properties(self) -> Properties:
        """Collection of acumulated Properties."""
        return self._properties

    @property
    def constraints(self) -> Constraints:
        """Collection of acumulated Constraints."""
        return self._constraints

    async def add(self, model: DemandOfferBaseModel):
        """Add properties and constraints from the given model to this demand definition."""

        properties, constraints = await model.serialize()

        self.add_properties(properties)
        self.add_constraints(constraints)

    def add_properties(self, props: Properties):
        """Add properties from the given dictionary to this demand definition."""
        self._properties.update(props)

    def add_constraints(self, constraints: Union[Constraint, ConstraintGroup]):
        """Add a constraint from given args to the demand definition."""
        self._constraints.items.extend(constraints)

    async def create_demand(self, node: "GolemNode") -> "Demand":
        """Create demand and subscribe to its events."""
        return await Demand.create_from_properties_constraints(
            node, self.properties, self.constraints
        )

    @classmethod
    async def from_demand(cls, demand: "Demand") -> "DemandBuilder":
        demand_data = deepcopy(await demand.get_data())

        return cls(demand_data.properties, [demand_data.constraints])
