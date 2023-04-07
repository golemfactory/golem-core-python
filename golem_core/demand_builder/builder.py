import abc
from typing import List, Dict, Any, TYPE_CHECKING

from golem_core.demand_builder.model import Model, join_str_constraints
from golem_core.low import Demand


if TYPE_CHECKING:
    from golem_core import GolemNode


class DemandBuilder:
    """Builds a dictionary of properties and constraints from high-level models.

    The dictionary represents a Demand object, which is later matched by the new Golem's
    market implementation against Offers coming from providers to find those providers
    who can satisfy the requestor's demand.

    example usage:

    ```python
    >>> from golem_core.demand_builder import props
    >>> from golem_core.demand_builder.builder import DemandBuilder
    >>> from datetime import datetime, timezone
    >>> builder = DemandBuilder()
    >>> await builder.add(props.NodeInfo(name="a node", subnet_tag="testnet"))
    >>> await builder.add(props.Activity(expiration=datetime.now(timezone.utc)))
    >>> print(builder)
    {'properties':
        {'golem.node.id.name': 'a node',
         'golem.node.debug.subnet': 'testnet',
         'golem.srv.comp.expiration': 1601655628772},
     'constraints': []}
    ```
    """

    def __init__(self):
        self._properties: Dict[str, Any] = {}
        self._constraints: List[str] = []

    def __repr__(self):
        return repr({
            "properties": self._properties,
            "constraints": self._constraints
        })

    @property
    def properties(self) -> Dict:
        """List of properties for this demand."""
        return self._properties

    @property
    def constraints(self) -> str:
        """Constraints definition for this demand."""
        return join_str_constraints(self._constraints)

    async def add(self, model: Model):
        """Add properties and constraints from the given model to this demand definition."""

        properties, constraints = await model.serialize()

        self.add_properties(properties)
        self.add_constraints(constraints)

    def add_properties(self, props: Dict):
        """Add properties from the given dictionary to this demand definition."""
        self._properties.update(props)

    def add_constraints(self, *constraints: str):
        """Add a constraint to the demand definition."""
        self._constraints.extend(constraints)

    async def decorate(self, *decorators: "DemandDecorator"):
        for decorator in decorators:
            await decorator.decorate_demand(self)

    async def create_demand(self, node: "GolemNode") -> Demand:
        return await Demand.create_from_properties_constraints(
            node,
            self.properties,
            self.constraints
        )


class DemandDecorator(abc.ABC):
    """An interface that specifies classes that can add properties and constraints through a \
    DemandBuilder."""

    @abc.abstractmethod
    async def decorate_demand(self, demand: DemandBuilder) -> None:
        """Add appropriate properties and constraints to a Demand."""
