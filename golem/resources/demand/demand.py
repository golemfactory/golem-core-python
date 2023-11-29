import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, AsyncIterator, Callable, Dict, List, Optional, Union, cast

from ya_market import RequestorApi
from ya_market import models as models

from golem.payload import Constraints, PayloadSyntaxParser, Properties
from golem.resources.base import _NULL, Resource, ResourceNotFound, api_call_wrapper
from golem.resources.demand.data import DemandData
from golem.resources.demand.events import DemandClosed, NewDemand
from golem.resources.proposal import Proposal
from golem.utils.low import YagnaEventCollector

if TYPE_CHECKING:
    from golem.node import GolemNode


class Demand(Resource[RequestorApi, models.Demand, _NULL, Proposal, _NULL], YagnaEventCollector):
    """A single demand on the Golem Network.

    Created with one of the :class:`Demand`-returning methods of the :any:`GolemNode`.
    """

    _demand_data: Optional[DemandData] = None

    def __init__(self, node: "GolemNode", id_: str, data: Optional[models.Demand] = None):
        super().__init__(node, id_, data)
        asyncio.create_task(node.event_bus.emit(NewDemand(self)))

    ######################
    #   EXTERNAL INTERFACE
    @api_call_wrapper(ignore=[404, 410])
    async def unsubscribe(self) -> None:
        """Stop all operations related to this demand and remove it.

        This is a final operation, unsubscribed demand is not available anymore.
        """
        self.set_no_more_children()
        self.stop_collecting_events()
        await self.api.unsubscribe_demand(self.id)
        await self.node.event_bus.emit(DemandClosed(self))

    async def initial_proposals(self) -> AsyncIterator["Proposal"]:
        """Yield initial proposals matched to this demand."""
        async for proposal in self.child_aiter():
            assert isinstance(proposal, Proposal)  # mypy
            if proposal.initial:
                yield proposal

    def proposal(self, proposal_id: str) -> "Proposal":
        """Return a :class:`Proposal` with a given ID."""
        proposal = Proposal(self.node, proposal_id)

        #   NOTE: we don't know the parent, so we don't set it, but demand is known
        if proposal._demand is None and proposal._parent is None:
            proposal.demand = self

        return proposal

    ###########################
    #   Event collector methods
    def _collect_events_kwargs(self) -> Dict:
        return {"timeout": 5, "max_events": 10}

    def _collect_events_args(self) -> List:
        return [self.id]

    @property
    def _collect_events_func(self) -> Callable:
        return self.api.collect_offers

    async def _process_event(
        self, event: Union[models.ProposalEvent, models.ProposalRejectedEvent]
    ) -> None:
        if isinstance(event, models.ProposalEvent):
            proposal = Proposal.from_proposal_event(self.node, event)
            parent = self._get_proposal_parent(proposal)
            parent.add_child(proposal)
        elif isinstance(event, models.ProposalRejectedEvent):
            assert event.proposal_id is not None  # mypy
            proposal = self.proposal(event.proposal_id)
            proposal.add_event(event)

    #################
    #   OTHER METHODS
    @api_call_wrapper()
    async def _get_data(self) -> models.Demand:
        #   NOTE: this method is required because there is no get_demand(id)
        #         in ya_market (as there is no matching endpoint in yagna)
        all_demands: List[models.Demand] = await self.api.get_demands()
        try:
            return next(d for d in all_demands if d.demand_id == self.id)
        except StopIteration:
            raise ResourceNotFound(self)

    @classmethod
    async def create_from_properties_constraints(
        cls,
        node: "GolemNode",
        properties: Properties,
        constraints: Constraints,
    ) -> "Demand":
        data = models.DemandOfferBase(
            properties=properties.serialize(),
            constraints=constraints.serialize(),
        )
        return await cls.create(node, data)

    @classmethod
    async def create(cls, node: "GolemNode", data: models.DemandOfferBase) -> "Demand":
        api = cls._get_api(node)
        demand_id = await api.subscribe_demand(data)
        return cls(node, demand_id)

    def _get_proposal_parent(self, proposal: "Proposal") -> Union["Demand", "Proposal"]:
        assert proposal.data is not None

        if proposal.data.state == "Initial":
            parent = self
        else:
            parent_proposal_id = proposal.data.prev_proposal_id
            parent = Proposal(self.node, parent_proposal_id)  # type: ignore
        return parent

    async def get_demand_data(self) -> DemandData:
        if not self._demand_data:
            data = await self.get_data()

            # TODO: Make constraints parsing lazy
            constraints = PayloadSyntaxParser.get_instance().parse_constraints(data.constraints)

            return DemandData(
                properties=Properties(data.properties),
                constraints=constraints,
                demand_id=data.demand_id,
                requestor_id=data.requestor_id,
                timestamp=cast(datetime, data.timestamp),
            )

        return self._demand_data
