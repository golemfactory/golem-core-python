import asyncio
from typing import AsyncIterator, Callable, Dict, List, Optional, TYPE_CHECKING, Union
from datetime import datetime, timedelta, timezone

from ya_market import RequestorApi, models as models
from ya_market.exceptions import ApiException

from golem_core.events import ResourceClosed
from .api_call_wrapper import api_call_wrapper
from .exceptions import ResourceNotFound
from .payment import Invoice
from .resource import Resource
from .resource_internals import _NULL
from .yagna_event_collector import YagnaEventCollector

if TYPE_CHECKING:
    from golem_core.golem_node import GolemNode
    from .activity import Activity  # TODO: do we really need this?


class Demand(Resource[RequestorApi, models.Demand, _NULL, "Proposal", _NULL], YagnaEventCollector):
    """A single demand on the Golem Network.

    Created with one of the :class:`Demand`-returning methods of the :any:`GolemNode`.
    """
    ######################
    #   EXTERNAL INTERFACE
    @api_call_wrapper(ignore=[404, 410])
    async def unsubscribe(self) -> None:
        """Stop all operations related to this demand and remove it.

        This is a final operation, unsubscribed demand is not available anymore."""
        self.set_no_more_children()
        self.stop_collecting_events()
        await self.api.unsubscribe_demand(self.id)
        self.node.event_bus.emit(ResourceClosed(self))

    async def initial_proposals(self) -> AsyncIterator["Proposal"]:
        """Yields initial proposals matched to this demand."""
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

    async def _process_event(self, event: Union[models.ProposalEvent, models.ProposalRejectedEvent]) -> None:
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
        properties: Dict[str, str],
        constraints: str,
    ) -> "Demand":
        data = models.DemandOfferBase(
            properties=properties,
            constraints=constraints,
        )
        return await cls.create(node, data)

    @classmethod
    async def create(cls, node: "GolemNode", data: models.DemandOfferBase) -> "Demand":
        api = cls._get_api(node)
        demand_id = await api.subscribe_demand(data)
        return cls(node, demand_id)

    def _get_proposal_parent(self, proposal: "Proposal") -> Union["Demand", "Proposal"]:
        assert proposal.data is not None

        if proposal.data.state == 'Initial':
            parent = self
        else:
            parent_proposal_id = proposal.data.prev_proposal_id
            parent = Proposal(self.node, parent_proposal_id)  # type: ignore
        return parent


class Proposal(
    Resource[
        RequestorApi,
        models.Proposal,
        Union["Demand", "Proposal"],
        Union["Proposal", "Agreement"],
        Union[models.ProposalEvent, models.ProposalRejectedEvent]
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
        return self.data.state == 'Draft'

    @property
    def rejected(self) -> bool:
        """True for rejected proposals. They will have no more :func:`responses`."""
        assert self.data is not None
        return self.data.state == 'Rejected'

    ###########################
    #   Tree-related methods
    @property
    def demand(self) -> "Demand":
        """Initial :class:`Demand` of this proposal."""
        # We can either have no parent (this is possible when this Proposal was created from id),
        # and then _demand is always set, or a Proposal-parent or a Demand-parent.
        if self._demand is not None:
            return self._demand
        else:
            if isinstance(self.parent, Demand):
                return self.parent
            else:
                return self.parent.demand

    @demand.setter
    def demand(self, demand: "Demand") -> None:
        assert self._demand is None
        assert self._parent is None  # Sanity check (there's no scenario where we have a parent and demand is set)
        self._demand = demand

    def add_event(self, event: Union[models.ProposalEvent, models.ProposalRejectedEvent]) -> None:
        super().add_event(event)
        if isinstance(event, models.ProposalRejectedEvent):
            self.set_no_more_children()

    async def responses(self) -> AsyncIterator["Proposal"]:
        """Yields responses to this proposal.

        Stops when the proposal is rejected.
        """
        async for child in self.child_aiter():
            if isinstance(child, Proposal):
                yield child

    ############################
    #   Negotiations
    @api_call_wrapper()
    async def create_agreement(self, autoclose: bool = True, timeout: timedelta = timedelta(seconds=60)) -> "Agreement":
        """Promote this proposal to an agreement.

        :param autoclose: Terminate the agreement when the :any:`GolemNode` closes.
        :param timeout: TODO - this is used as `AgreementValidTo`, but what is it exactly?
        """
        proposal = models.AgreementProposal(
            proposal_id=self.id,
            valid_to=datetime.now(timezone.utc) + timeout,  # type: ignore  # TODO: what is AgreementValidTo?
        )
        agreement_id = await self.api.create_agreement(proposal)
        agreement = Agreement(self.node, agreement_id)
        self.add_child(agreement)
        if autoclose:
            self.node.add_autoclose_resource(agreement)

        return agreement

    @api_call_wrapper()
    async def reject(self, reason: str = '') -> None:
        """Reject the proposal - inform the provider that we won't send any more counter-proposals.

        :param reason: An optional information for the provider describing rejection reasons.

        Invalid on our responses.
        """
        await self.api.reject_proposal_offer(
            self.demand.id, self.id, request_body={"message": reason}, _request_timeout=5
        )

    @api_call_wrapper()
    async def respond(self) -> "Proposal":
        """Respond to a proposal with a counter-proposal.

        Invalid on our responses.

        TODO: all the negotiation logic should be reflected in params of this method,
        but negotiations are not implemented yet. Related issues:
        https://github.com/golemfactory/golem-core-python/issues/17
        https://github.com/golemfactory/golem-core-python/issues/18
        """

        data = await self._response_data()
        new_proposal_id = await self.api.counter_proposal_demand(self.demand.id, self.id, data, _request_timeout=5)

        new_proposal = type(self)(self.node, new_proposal_id)
        self.add_child(new_proposal)

        return new_proposal

    async def _response_data(self) -> models.DemandOfferBase:
        # FIXME: this is a mock
        demand_data = await self.demand.get_data()
        data = models.DemandOfferBase(properties=demand_data.properties, constraints=demand_data.constraints)
        return data

    ##########################
    #   Other
    async def _get_data(self) -> models.Proposal:
        assert self.demand is not None
        data: models.Proposal = await self.api.get_proposal_offer(self.demand.id, self.id)
        if data.state == "Rejected":
            self.set_no_more_children()
        return data

    @classmethod
    def from_proposal_event(cls, node: "GolemNode", event: models.ProposalEvent) -> "Proposal":
        data = event.proposal
        assert data.proposal_id is not None  # mypy
        proposal = Proposal(node, data.proposal_id, data)
        proposal.add_event(event)
        return proposal


class Agreement(Resource[RequestorApi, models.Agreement, "Proposal", "Activity", _NULL]):
    """A single agreement on the Golem Network.

    Sample usage::

        agreement = await proposal.create_agreement()
        await agreement.confirm()
        await agreement.wait_for_approval()
        activity = await agreement.create_activity()
        # Use the activity
        await agreement.terminate()
    """
    @api_call_wrapper()
    async def confirm(self) -> None:
        """Confirm the agreement.

        First step that leads to an active agreement.
        """
        await self.api.confirm_agreement(self.id, app_session_id=self.node.app_session_id)

    @api_call_wrapper()
    async def wait_for_approval(self) -> bool:
        """Wait for provider's approval of the agreement.

        Second (and last) step leading to an active agreement.

        :returns: True if agreement was approved.
        """
        try:
            await self.api.wait_for_approval(self.id, timeout=15, _request_timeout=16)
            return True
        except ApiException as e:
            if e.status == 410:
                return False
            elif e.status == 408:
                #   TODO: maybe this should be in api_call_wrapper?
                return await self.wait_for_approval()
            else:
                raise

    @api_call_wrapper()
    async def create_activity(self, autoclose: bool = True, timeout: timedelta = timedelta(seconds=10)) -> "Activity":
        """Create a new :any:`Activity` for this :any:`Agreement`.

        :param autoclose: Destroy the activity when the :any:`GolemNode` closes.
        :param timeout: Request timeout.
        """
        from .activity import Activity
        activity = await Activity.create(self.node, self.id, timeout)
        if autoclose:
            self.node.add_autoclose_resource(activity)
        self.add_child(activity)
        return activity

    @api_call_wrapper()
    async def terminate(self, reason: str = '') -> None:
        """Terminate the agreement.

        :param reason: Optional information for the provider explaining why the agreement was terminated.
        """
        try:
            await self.api.terminate_agreement(self.id, request_body={"message": reason})
        except ApiException as e:
            if self._is_permanent_410(e):
                pass
            else:
                raise

        self.node.event_bus.emit(ResourceClosed(self))

    @property
    def invoice(self) -> Optional[Invoice]:
        """:any:`Invoice` for this :any:`Agreement`, or None if we didn't yet receive an invoice."""
        try:
            return [child for child in self.children if isinstance(child, Invoice)][0]
        except IndexError:
            return None

    @property
    def activities(self) -> List["Activity"]:
        """A list of :any:`Activity` created for this :any:`Agreement`."""
        from .activity import Activity  # circular imports prevention
        return [child for child in self.children if isinstance(child, Activity)]

    async def close_all(self) -> None:
        """Terminate agreement, destroy all activities. Ensure success -> retry if there are any problems.

        This is indended to be used in scenarios when we just want to end
        this agreement and we want to make sure it is really terminated (even if e.g. in some other
        separate task we're waiting for the provider to approve it).
        """
        #   TODO: This method is very ugly, also similar method could be useful for acivity only.
        #   BUT this probably should be a yagna-side change. Agreement.terminate() should
        #   just always succeed, as well as Activity.destroy() - yagna should repeat if necessary etc.
        #   We should only repeat in rare cases when we can't connect to our local `yagna`.
        #   Related issue: https://github.com/golemfactory/golem-core-python/issues/19

        #   Q: Why limit on repeats?
        #   A: So that we don't flood `yagna` with requests that will never succeed.
        #   Q: Why repeating 4 times?
        #   A: No particular reason.

        for i in range(1, 5):
            try:
                await self.terminate()
                break
            except ApiException as e:
                if self._is_permanent_410(e):
                    break
            await asyncio.sleep(2 ** i)

        for activity in self.activities:
            for i in range(1, 5):
                try:
                    await activity.destroy()
                    break
                except Exception:
                    pass
                await asyncio.sleep(2 ** i)

    @staticmethod
    def _is_permanent_410(e: ApiException) -> bool:
        #   TODO: Remove this check once https://github.com/golemfactory/yagna/issues/2264 is done
        #         and every 410 is permanent.
        if e.status != 410:
            return False
        return "from Approving" not in str(e) and "from Pending" not in str(e)
