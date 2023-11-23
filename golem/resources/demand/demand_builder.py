from copy import deepcopy
from typing import TYPE_CHECKING, Optional, Union

from golem.payload import Payload
from golem.payload.constraints import Constraint, ConstraintGroup, Constraints
from golem.payload.properties import Properties
from golem.resources.demand.demand import Demand

if TYPE_CHECKING:
    from golem.node import GolemNode


class DemandBuilder:
    """Builder that gives ability to collect Demand's properties and constraints in multiple \
    separate steps, prior its creation.

    example usage:

    ```python
    >>> from golem.resources import DemandBuilder
    >>> from golem.payload import defaults
    >>> from datetime import datetime, timezone
    >>> builder = DemandBuilder()
    >>> await builder.add(defaults.NodeInfo(name="a node", subnet_tag="testnet"))
    >>> await builder.add(defaults.ActivityInfo(expiration=datetime.now(timezone.utc)))
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
        self.properties: Properties = (
            deepcopy(properties) if properties is not None else Properties()
        )
        self.constraints: Constraints = (
            deepcopy(constraints) if constraints is not None else Constraints()
        )

    def __repr__(self):
        return repr({"properties": self.properties, "constraints": self.constraints})

    def __eq__(self, other):
        return (
            isinstance(other, DemandBuilder)
            and self.properties == other.properties
            and self.constraints == other.constraints
        )

    async def add(self, payload: Payload):
        """Add properties and constraints from the given payload to this demand definition."""

        properties, constraints = await payload.build_properties_and_constraints()

        self.add_properties(properties)
        self.add_constraints(constraints)

    def add_properties(self, props: Properties):
        """Add properties from the given dictionary to this demand definition."""
        self.properties.update(props)

    def add_constraints(self, constraints: Union[Constraint, ConstraintGroup]):
        """Add a constraint from given args to the demand definition."""
        if (
            isinstance(constraints, ConstraintGroup)
            and constraints.operator == self.constraints.operator
        ):
            self.constraints.items.extend(constraints.items)
        else:
            self.constraints.items.append(constraints)

    async def create_demand(self, node: "GolemNode") -> "Demand":
        """Create demand and subscribe to its events."""
        return await Demand.create_from_properties_constraints(
            node, self.properties, self.constraints
        )
