import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, AsyncIterator, Literal, Optional, Union

from ya_market import RequestorApi
from ya_market import models as models

from golem.payload import Constraints, Properties
from golem.resources.agreement import Agreement
from golem.resources.base import Resource, api_call_wrapper
from golem.resources.proposal.events import NewProposal
from golem.resources.proposal.exceptions import ProposalRejected

if TYPE_CHECKING:
    from golem.node import GolemNode
    from golem.resources.demand import Demand


ProposalId = str

# TODO: Use Enum
ProposalState = Literal["Initial", "Draft", "Rejected", "Accepted", "Expired"]


@dataclass
class ProposalData:
    properties: Properties
    constraints: Constraints
    proposal_id: Optional[ProposalId]
    issuer_id: Optional[str]
    state: ProposalState
    timestamp: datetime
    prev_proposal_id: Optional[str]


class Proposal(
    Resource[
        RequestorApi,
        models.Proposal,
        Union["Demand", "Proposal"],
        Union["Proposal", Agreement],
        Union[models.ProposalEvent, models.ProposalRejectedEvent],
    ]
):
    """A single proposal on the Golem Network.

    Either a initial proposal matched to a demand, or a counter-proposal sent
    either by us or by the provider.

    Sample usage::

        initial_proposal = await demand.initial_proposals().__anext__()
        our_counter_proposal = await initial_proposal.respond()
        async for their_counter_proposal in our_counter_proposal.responses():
            agreement = their_counter_proposal.create_agreement()
            break
        else:
            print("Our counter-proposal was rejected :(")
    """

    _demand: Optional["Demand"] = None

    def __init__(self, node: "GolemNode", id_: str, data: Optional[models.Proposal] = None):
        super().__init__(node, id_, data)
        asyncio.create_task(node.event_bus.emit(NewProposal(self)))

    ##############################
    #   State-related properties
    @property
    def initial(self) -> bool:
        """True for proposals matched directly to the demand."""
        return self.parent == self.demand

    @property
    def draft(self) -> bool:
        """True for proposals that are responses to other proposals."""
        assert self.data is not None
        return self.data.state == "Draft"

    @property
    def rejected(self) -> bool:
        """True for rejected proposals. They will have no more :func:`responses`."""
        assert self.data is not None
        return self.data.state == "Rejected"

    ###########################
    #   Tree-related methods
    @property
    def demand(self) -> "Demand":
        """Initial :class:`Demand` of this proposal."""
        # We can either have no parent (this is possible when this Proposal was created from id),
        # and then _demand is always set, or a Proposal-parent or a Demand-parent.

        # FIXME: remove local import
        from golem.resources import Demand

        if self._demand is not None:
            return self._demand
        else:
            if isinstance(self.parent, Demand):
                return self.parent
            else:
                return self.parent.demand  # TODO recursion

    @demand.setter
    def demand(self, demand: "Demand") -> None:
        assert self._demand is None
        assert (
            self._parent is None
        )  # Sanity check (there's no scenario where we have a parent and demand is set)
        self._demand = demand

    def add_event(self, event: Union[models.ProposalEvent, models.ProposalRejectedEvent]) -> None:
        super().add_event(event)
        if isinstance(event, models.ProposalRejectedEvent):
            self.set_no_more_children(ProposalRejected(event.proposal_id, event.reason.message))

    async def responses(self) -> AsyncIterator["Proposal"]:
        """Yield responses to this proposal.

        Stops when the proposal is rejected.
        """
        async for child in self.child_aiter():
            if isinstance(child, Proposal):
                yield child

    ############################
    #   Negotiations
    @api_call_wrapper()
    async def create_agreement(
        self, autoclose: bool = True, timeout: timedelta = timedelta(seconds=60)
    ) -> "Agreement":
        """Promote this proposal to an agreement.

        :param autoclose: Terminate the agreement when the :any:`GolemNode` closes.
        :param timeout: TODO - this is used as `AgreementValidTo`, but what is it exactly?
        """
        proposal = models.AgreementProposal(
            proposal_id=self.id,
            # TODO: what is AgreementValidTo?
            valid_to=datetime.now(timezone.utc) + timeout,  # type: ignore
        )
        agreement_id = await self.api.create_agreement(proposal)
        agreement = Agreement(self.node, agreement_id)
        self.add_child(agreement)
        if autoclose:
            self.node.add_autoclose_resource(agreement)

        return agreement

    @api_call_wrapper()
    async def reject(self, reason: str = "") -> None:
        """Reject the proposal - inform the provider that we won't send any more counter-proposals.

        :param reason: An optional information for the provider describing rejection reasons.

        Invalid on our responses.
        """
        await self.api.reject_proposal_offer(
            self.demand.id, self.id, request_body={"message": reason}, _request_timeout=5
        )

    @api_call_wrapper()
    async def respond(
        self, properties: Optional[Properties] = None, constraints: Optional[Constraints] = None
    ) -> "Proposal":
        """Respond to a proposal with a counter-proposal.

        Invalid on our responses.

        Related issues:
        https://github.com/golemfactory/golem-core-python/issues/17
        https://github.com/golemfactory/golem-core-python/issues/18
        """
        if properties is None and constraints is None:
            data = await self._response_data()
        elif properties is not None and constraints is not None:
            data = models.DemandOfferBase(
                properties=properties.serialize(), constraints=constraints.serialize()
            )
        else:
            raise ValueError("Both `properties` and `constraints` arguments must be provided!")

        new_proposal_id = await self.api.counter_proposal_demand(
            self.demand.id, self.id, data, _request_timeout=5
        )

        new_proposal = type(self)(self.node, new_proposal_id)
        self.add_child(new_proposal)

        return new_proposal

    async def _response_data(self) -> models.DemandOfferBase:
        demand_data = await self.demand.get_data()
        data = models.DemandOfferBase(
            properties=demand_data.properties, constraints=demand_data.constraints
        )
        return data

    ##########################
    #   Other
    async def _get_data(self) -> models.Proposal:
        assert self.demand is not None
        data: models.Proposal = await self.api.get_proposal_offer(self.demand.id, self.id)
        if data.state == "Rejected":
            self.set_no_more_children(
                ProposalRejected(data.proposal_id, "Proposal found at `Rejected` state")
            )
        return data

    @classmethod
    def from_proposal_event(cls, node: "GolemNode", event: models.ProposalEvent) -> "Proposal":
        data = event.proposal
        assert data.proposal_id is not None  # mypy
        proposal = Proposal(node, data.proposal_id, data)
        proposal.add_event(event)
        return proposal
