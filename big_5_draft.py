import asyncio
from typing import Callable, List, Optional

from golem_core.core.market_api import RepositoryVmPayload
from golem_core.managers.activity.single_use import SingleUseActivityManager
from golem_core.managers.agreement.queue import QueueAgreementManager
from golem_core.managers.base import WorkContext
from golem_core.managers.payment.pay_all import PayAllPaymentManager
from golem_core.managers.work.decorators import (
    redundancy_cancel_others_on_first_done,
    retry,
    work_decorator,
)
from golem_core.managers.work.sequential import SequentialWorkManager
















class ConfirmAllNegotiationManager:
    def __init__(self, get_allocation: "Callable", payload, event_bus):
        self._event_bus = event_bus
        self._get_allocation = get_allocation
        self._allocation = self._get_allocation()
        self._payload = payload
        demand_builder = DemandBuilder()
        demand_builder.add(self._payload)
        demand_builder.add(self._allocation)
        self._demand = demand_builder.create_demand()

    def negotiate(self):
        for initial in self._demand.get_proposals():  # infinite loop
            pending = initial.respond()
            confirmed = pending.confirm()
            self._event_bus.register(ProposalConfirmed(demand=self._demand, proposal=confirmed))


def filter_blacklist(proposal: "Proposal") -> bool:
    providers_blacklist: List[str] = ...
    return proposal.provider_id in providers_blacklist


class FilterNegotiationManager:
    INITIAL = "INITIAL"
    PENDING = "PENDING"

    def __init__(self, get_allocation: "Callable", payload, event_bus):
        self._event_bus = event_bus
        self._get_allocation = get_allocation
        self._allocation = self._get_allocation()
        self._payload = payload
        demand_builder = DemandBuilder()
        demand_builder.add(self._payload)
        demand_builder.add(self._allocation)
        self._demand = demand_builder.create_demand()
        self._filters = {
            self.INITIAL: [],
            self.PENDING: [],
        }

    def add_filter(self, filter: "Filter", type: str):
        self._filters[type].append(filter)

    def _filter(self, initial: "Proposal", type: str) -> bool:
        for f in self._filters[type]:
            if f(initial):
                return True
        return False

    def negotiate(self):
        for initial in self._demand.get_proposals():  # infinite loop
            if self._filter(initial, self.INITIAL):
                continue

            pending = initial.respond()
            if self._filter(pending, self.PENDING):
                pending.reject()
                continue

            confirmed = pending.confirm()
            self._event_bus.register(ProposalConfirmed(demand=self._demand, proposal=confirmed))


class AcceptableRangeNegotiationManager:
    def __init__(self, get_allocation: "Callable", payload, event_bus):
        self._event_bus = event_bus
        self._get_allocation = get_allocation
        self._allocation = self._get_allocation()
        self._payload = payload
        demand_builder = DemandBuilder()
        demand_builder.add(self._payload)
        demand_builder.add(self._allocation)
        self._demand = demand_builder.create_demand()

    def negotiate(self):
        for initial in self._demand.get_proposals():  # infinite loop
            pending = self._negotiate_for_accepted_range(initial)
            if pending is None:
                continue
            confirmed = pending.confirm()
            self._event_bus.register(ProposalConfirmed(demand=self._demand, proposal=confirmed))

    def _validate_values(self, proposal: "Proposal") -> bool:
        """Checks if proposal's values are in accepted range

        e.g.
        True
        x_accepted range: [2,10]
        proposal.x: 9

        False
        x_accepted range: [2,10]
        proposal.x: 11
        """

    def _middle_values(self, our: "Proposal", their: "Proposal") -> Optional["Proposal"]:
        """Create new proposal with new values in accepted range based on given proposals.

        If middle values are outside of accepted range return None

        e.g.
        New proposal
        x_accepted range: [2,10]
        our.x: 5
        their.x : 13
        new: (5+13)//2 -> 9

        None
        x_accepted range: [2,10]
        our.x: 9
        their.x : 13
        new: (9+13)//2 -> 11 -> None
        """

    def _negotiate_for_accepted_range(self, our: "Proposal"):
        their = our.respond()
        while True:
            if self._validate_values(their):
                return their
            our = self._middle_values(our, their)
            if our is None:
                return None
            their = their.respond_with(our)


def blacklist_offers(blacklist: "List"):
    def _blacklist_offers(func):
        def wrapper(*args, **kwargs):
            while True:
                offer = func()

                if offer not in blacklist:
                    return offer

        return wrapper

    return _blacklist_offers


class LifoOfferManager:
    _offers: List["Offer"]

    def __init__(self, event_bus) -> None:
        self._event_bus = event_bus
        self._event_bus.resource_listen(self.on_new_offer, ProposalConfirmed)

    def on_new_offer(self, offer: "Offer") -> None:
        self._offers.append(offer)

    def get_offer(self) -> "Offer":
        while True:
            try:
                return self._offers.pop()
            except IndexError:
                # wait for offers
                # await sleep
                pass














@work_decorator(redundancy_cancel_others_on_first_done(size=5))
@work_decorator(retry(tries=5))
async def work(context: WorkContext):
    await context.run("echo hello world")


async def work_service(context: WorkContext):
    await context.run("app --daemon")


async def work_service_fetch(context: WorkContext):
    await context.run("app --daemon &")

    while await context.run("app check-if-running"):
        await asyncio.sleep(1)


async def work_batch(context: WorkContext):
    batch = await context.create_batch()
    batch.run("echo 1")
    batch.run("echo 2")
    batch.run("echo 3")

    await batch()


async def main():
    payload = RepositoryVmPayload(image_hash="...")
    budget = 1.0
    work_list = [
        work,
        work,
        work,
    ]
    event_bus = EventBus()

    payment_manager = PayAllPaymentManager(budget, event_bus)

    negotiation_manager = FilterNegotiationManager(
        payment_manager.get_allocation, payload, event_bus
    )
    negotiation_manager.add_filter(filter_blacklist, negotiation_manager.INITIAL)
    negotiation_manager.negotiate()  # run in async, this will generate ProposalConfirmed events

    offer_manager = LifoOfferManager(event_bus)  # listen to ProposalConfirmed

    agreement_manager = QueueAgreementManager(
        blacklist_offers(["banned_node_id"])(offer_manager.get_offer)
    )

    activity_manager = SingleUseActivityManager(
        agreement_manager.get_agreement,
    )

    work_manager = SequentialWorkManager(activity_manager.do_work)
    await work_manager.do_work_list(work_list)


if __name__ == "__main__":
    asyncio.run(main())
