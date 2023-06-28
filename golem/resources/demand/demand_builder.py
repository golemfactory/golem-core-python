from copy import deepcopy
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Iterable, Optional, Union

from golem.payload import Payload
from golem.payload import defaults as payload_defaults
from golem.payload.constraints import Constraint, ConstraintGroup, Constraints
from golem.payload.parsers.base import PayloadSyntaxParser
from golem.payload.properties import Properties
from golem.resources.allocation.allocation import Allocation
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

    async def add_default_parameters(
        self,
        parser: PayloadSyntaxParser,
        subnet: Optional[str] = None,
        expiration: Optional[datetime] = None,
        allocations: Iterable[Allocation] = (),
    ) -> None:
        """Add default parameters for Demand.

        :param payload: Details of the demand
        :param subnet: Subnet tag
        :param expiration: Timestamp when all agreements based on this demand will expire
            TODO: is this correct?
        :param allocations: Allocations that will be included in the description of this demand.
        """
        # FIXME: get rid of local import
        from golem.node import DEFAULT_EXPIRATION_TIMEOUT, SUBNET

        if subnet is None:
            subnet = SUBNET

        if expiration is None:
            expiration = datetime.now(timezone.utc) + DEFAULT_EXPIRATION_TIMEOUT

        await self.add(payload_defaults.ActivityInfo(expiration=expiration, multi_activity=True))
        await self.add(payload_defaults.NodeInfo(subnet_tag=subnet))

        for allocation in allocations:
            properties, constraints = await allocation.get_properties_and_constraints_for_demand(
                parser
            )

            self.add_constraints(constraints)
            self.add_properties(properties)

    async def create_demand(self, node: "GolemNode") -> "Demand":
        """Create demand and subscribe to its events."""
        return await Demand.create_from_properties_constraints(
            node, self.properties, self.constraints
        )
