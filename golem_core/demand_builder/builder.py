import abc
from typing import List, Dict, Any, Iterable

from golem_core.demand_builder.model import Model, constraint_model_serialize, join_str_constraints


class DemandBuilder:
    """Builds a dictionary of properties and constraints from high-level models.

    The dictionary represents a Demand object, which is later matched by the new Golem's
    market implementation against Offers coming from providers to find those providers
    who can satisfy the requestor's demand.

    example usage:

    ```python
    >>> import yapapi
    >>> from yapapi import props as yp
    >>> from yapapi.props.builder import DemandBuilder
    >>> from datetime import datetime, timezone
    >>> builder = DemandBuilder()
    >>> builder.add(yp.NodeInfo(name="a node", subnet_tag="testnet"))
    >>> builder.add(yp.Activity(expiration=datetime.now(timezone.utc)))
    >>> builder.__repr__
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
        return repr({"properties": self._properties, "constraints": self._constraints})

    @property
    def properties(self) -> Dict:
        """List of properties for this demand."""
        return self._properties

    @property
    def constraints(self) -> str:
        """Constraints definition for this demand."""
        return join_str_constraints(self._constraints)

    def add(self, model: Model):
        """Add properties and constraints from the given model to this demand definition."""

        self.add_properties(model.serialize_properties())
        self.add_constraint(model.serialize_constraints())

    def add_properties(self, props: Dict):
        """Add properties from the given dictionary to this demand definition."""
        self._properties.update(props)

    def add_constraint(self, constraint: str):
        """Add a constraint to the demand definition."""
        self._constraints.append(constraint)

    def add_constraints(self, constraints: Iterable[str]):
        """Add a constraint to the demand definition."""
        self._constraints.extend(constraints)

    async def decorate(self, *decorators: "DemandDecorator"):
        for decorator in decorators:
            await decorator.decorate_demand(self)


class DemandDecorator(abc.ABC):
    """An interface that specifies classes that can add properties and constraints through a \
    DemandBuilder."""

    @abc.abstractmethod
    async def decorate_demand(self, demand: DemandBuilder) -> None:
        """Add appropriate properties and constraints to a Demand."""


class AutodecoratingModel(Model, DemandDecorator):
    """Base class, implementing the DemandDecorator interface to automatically decorate a demand \
    using the model's properties and constraints.

    example:
    ```python
    >>> import asyncio
    >>> from dataclasses import dataclass
    >>> from yapapi.props import prop, constraint
    >>> from yapapi.props.builder import AutodecoratingModel, DemandBuilder
    >>>
    >>> @dataclass
    ... class Foo(AutodecoratingModel):
    ...     bar: str = prop("some.bar")
    ...     max_baz: int = constraint("baz", "<=", 100)
    ...
    >>> async def main():
    ...     foo = Foo(bar="a nice one", max_baz=50)
    ...     demand = DemandBuilder()
    ...     await foo.decorate_demand(demand)
    ...     print(demand)
    ...
    >>> asyncio.run(main())
    {'properties': {'some.bar': 'a nice one'}, 'constraints': ['((baz<=50))']}
    ```
    """

    async def decorate_demand(self, demand: DemandBuilder):
        demand.add(self)
        demand.ensure(join_str_constraints(constraint_model_serialize(self)))
