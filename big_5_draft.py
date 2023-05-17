import asyncio
from abc import ABC
from functools import partial, wraps
from typing import List, Optional, Callable, Awaitable

from golem_core.core.market_api import RepositoryVmPayload


class Batch:
    def deploy(self):
        pass

    def start(self):
        pass

    def terminate(self):
        pass

    def run(self, command: str):
        pass

    async def __call__(self):
        pass


class WorkContext:
    async def deploy(self):
        pass

    async def start(self):
        pass

    async def terminate(self):
        pass

    async def run(self, command: str):
        pass

    async def create_batch(self) -> Batch:
        pass


class WorkResult:
    pass


WorkDecorator = Callable[['DoWorkCallable'], 'DoWorkCallable']

class Work(ABC):
    _work_decorators: Optional[List[WorkDecorator]]

    def __call__(self, context: WorkContext) -> Optional[WorkResult]:
        pass

DoWorkCallable = Callable[[Work], Awaitable[WorkResult]]

class PayAllPaymentManager:
    def __init__(self, budget, event_bus):
        self._budget = budget
        self._event_bus = event_bus

        self._allocation = Allocation.create(budget=self._budget)

        event_bus.register(InvoiceReceived(allocation=self._allocation), self.on_invoice_received)
        event_bus.register(DebitNoteReceived(allocation=self._allocation), self.on_debit_note_received)

    def get_allocation(self) -> 'Allocation':
        return self._allocation

    def on_invoice_received(self, invoice: 'Invoice') -> None:
        invoice.pay()

    def on_debit_note_received(self, debit_note: 'DebitNote') -> None:
        debit_note.pay()


class ConfirmAllNegotiationManager:
    def __init__(self, get_allocation: 'Callable', payload, event_bus):
        self._event_bus = event_bus
        self._get_allocation = get_allocation
        self._allocation = self._get_allocation()
        self._payload = payload
        demand_builder = DemandBuilder()
        demand_builder.add(self._payload)
        demand_builder.add(self._allocation)
        self._demand = demand_builder.create_demand()

    def negotiate(self):
        for initial in self._demand.get_proposals(): # infinite loop
            pending = initial.respond()
            confirmed = pending.confirm()
            self._event_bus.register(ProposalConfirmed(demand=self._demand, proposal=confirmed))

def filter_blacklist(proposal: 'Proposal') -> bool:
    providers_blacklist: List[str] = ...
    return proposal.provider_id in providers_blacklist

class FilterNegotiationManager:
    INITIAL="INITIAL"
    PENDING="PENDING"

    def __init__(self, get_allocation: 'Callable', payload, event_bus):
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

    def add_filter(self, filter: 'Filter', type: str):
        self._filters[type].append(filter)

    def _filter(self, initial: 'Proposal', type: str) -> bool:
        for f in self._filters[type]:
            if f(initial):
                return True
        return False

    def negotiate(self):
        for initial in self._demand.get_proposals(): # infinite loop
            if self._filter(initial, self.INITIAL):
                continue

            pending = initial.respond()
            if self._filter(pending, self.PENDING):
                pending.reject()
                continue

            confirmed = pending.confirm()
            self._event_bus.register(ProposalConfirmed(demand=self._demand, proposal=confirmed))


class AcceptableRangeNegotiationManager:
    def __init__(self, get_allocation: 'Callable', payload, event_bus):
        self._event_bus = event_bus
        self._get_allocation = get_allocation
        self._allocation = self._get_allocation()
        self._payload = payload
        demand_builder = DemandBuilder()
        demand_builder.add(self._payload)
        demand_builder.add(self._allocation)
        self._demand = demand_builder.create_demand()

    def negotiate(self):
        for initial in self._demand.get_proposals(): # infinite loop
            pending = self._negotiate_for_accepted_range(initial)
            if pending is None:
                continue
            confirmed = pending.confirm()
            self._event_bus.register(ProposalConfirmed(demand=self._demand, proposal=confirmed))

    def _validate_values(self, proposal: 'Proposal') -> bool:
        """Checks if proposal's values are in accepted range

        e.g.
        True
        x_accepted range: [2,10]
        proposal.x: 9

        False
        x_accepted range: [2,10]
        proposal.x: 11
        """

    def _middle_values(self, our: 'Proposal', their: 'Proposal') -> Optional['Proposal']:
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

    def _negotiate_for_accepted_range(self, our: 'Proposal'):
        their = our.respond()
        while True:
            if self._validate_values(their):
                return their
            our = self._middle_values(our, their)
            if our is None:
                return None
            their = their.respond_with(our)



def blacklist_offers(blacklist: 'List'):
    def _blacklist_offers(func):
        def wrapper(*args, **kwargs):
            while True:
                offer = func()

                if offer not in blacklist:
                    return offer

        return wrapper

    return _blacklist_offers

class LifoOfferManager:
    _offers: List['Offer']

    def __init__(self, event_bus) -> None:
        self._event_bus = event_bus
        self._event_bus.resource_listen(self.on_new_offer, ProposalConfirmed)

    def on_new_offer(self, offer: 'Offer') -> None:
        self._offers.append(offer)

    def get_offer(self) -> 'Offer':
        while True:
            try:
                return self._offers.pop()
            except IndexError:
                # wait for offers
                # await sleep
                pass

class FifoAgreementManager:
    def __init__(self, get_offer: 'Callable'):
        self.get_offer = get_offer

    def get_agreement(self) -> 'Agreement':
        while True:
            offer = self.get_offer()

            try:
                return offer.create_agrement()
            except Exception:
                pass

        # TODO: Close agreement


class SingleUseActivityManager:
    def __init__(self, get_agreement: 'Callable', on_activity_begin: Optional[Work] = None, on_activity_end: Optional[Work] = None):
        self._get_agreement = get_agreement
        self._on_activity_begin = on_activity_begin
        self._on_activity_end = on_activity_end

    async def get_activity(self) -> 'Activity':
        while True:
            # We need to release agreement if is not used
            agreement = await self._get_agreement()
            try:
                return await agreement.create_activity()
            except Exception:
                pass

    async def do_work(self, work) -> WorkResult:
        activity = await self.get_activity()

        if self._on_activity_begin:
            await activity.do(self._on_activity_begin)

        try:
            result = await activity.do(work)
        except Exception as e:
            result = WorkResult(exception=e)

        if self._on_activity_end:
            await activity.do(self._on_activity_end)

        return result


class SequentialWorkManager:
    def __init__(self, do_work: DoWorkCallable):
        self._do_work = do_work

    def apply_work_decorators(self, do_work: DoWorkCallable, work: Work) -> DoWorkCallable:
        if not hasattr(work, '_work_decorators'):
            return do_work

        result = do_work
        for dec in work._work_decorators:
            result = partial(dec, result)

        return result

    async def do_work(self, work: Work) -> WorkResult:
        decorated_do_work = self.apply_work_decorators(self._do_work, work)

        return await decorated_do_work(work)


    async def do_work_list(self, work_list: List[Work]) -> List[WorkResult]:
        results = []

        for work in work_list:
            results.append(
                await self.do_work(work)
            )

        return results


def retry(tries: int = 3):
    def _retry(do_work: DoWorkCallable) -> DoWorkCallable:
        @wraps(do_work)
        async def wrapper(work: Work) -> WorkResult:
            count = 0
            errors = []

            while count <= tries:
                try:
                    return await do_work(work)
                except Exception as err:
                    count += 1
                    errors.append(err)

            raise errors  # List[Exception] to Exception

        return wrapper

    return _retry


def redundancy_cancel_others_on_first_done(size: int = 3):
    def _redundancy(do_work: DoWorkCallable):
        @wraps(do_work)
        async def wrapper(work: Work) -> WorkResult:
            tasks = [do_work(work) for _ in range(size)]

            tasks_done, tasks_pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

            for task in tasks_pending:
                task.cancel()

            for task in tasks_pending:
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            return tasks_done.pop().result()

        return wrapper

    return _redundancy


async def default_on_activity_begin(context: WorkContext):
    batch = await context.create_batch()
    batch.deploy()
    batch.start()
    await batch()

    # After this function call we should have check if activity is actually started


async def default_on_activity_end(context: WorkContext):
    await context.terminate()

    # After this function call we should have check if activity is actually terminated


def work_decorator(decorator: WorkDecorator):
    def _work_decorator(work: Work):
        if not hasattr(work, '_work_decorators'):
            work._work_decorators = []

        work._work_decorators.append(decorator)

        return work

    return _work_decorator


@work_decorator(redundancy_cancel_others_on_first_done(size=5))
@work_decorator(retry(tries=5))
async def work(context: WorkContext):
    await context.run('echo hello world')


async def work_service(context: WorkContext):
    await context.run('app --daemon')


async def work_service_fetch(context: WorkContext):
    await context.run('app --daemon &')

    while await context.run('app check-if-running'):
        await asyncio.sleep(1)


async def work_batch(context: WorkContext):
    batch = await context.create_batch()
    batch.run('echo 1')
    batch.run('echo 2')
    batch.run('echo 3')

    await batch()


def main():
    payload = RepositoryVmPayload(image_hash='...')
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
    negotiation_manager.negotiate() # run in async, this will generate ProposalConfirmed events

    offer_manager = LifoOfferManager(event_bus) # listen to ProposalConfirmed

    agreement_manager = FifoAgreementManager(
        blacklist_offers(['banned_node_id'])(offer_manager.get_offer)
    )

    activity_manager = SingleUseActivityManager(
        agreement_manager.get_agreement,
        on_activity_begin=default_on_activity_begin,
        on_activity_end=default_on_activity_end,
    )

    work_manager = SequentialWorkManager(activity_manager.do_work)
    await work_manager.do_work_list(work_list)
