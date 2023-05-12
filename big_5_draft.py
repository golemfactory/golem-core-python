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


class FifoOfferManager:
    def __init__(self, get_allocation: 'Callable', event_bus):
        self._event_bus = event_bus
        self._proposals = []
        self.get_allocation = get_allocation

    def collect_proposals_for(self, payload) -> None:
        allocation = self.get_allocation()

        demand_builder = DemandBuilder()
        demand_builder.add(payload)
        demand_builder.add(allocation)
        demand = demand_builder.create_demand()
        self._proposals = demand.initial_proposals()

        self._event_bus.register(ProposalReceived(demand=demand), self.on_new_proposal)

    def on_new_proposal(self, proposal: 'Proposal') -> None:
        self._proposals.append(proposal)

    def get_proposal(self) -> 'Proposal':
        return self._proposals.pop()

    def get_offer(self) -> 'Offer':
        while True:
            provider_proposal = self.get_proposal()
            our_response = provider_proposal.respond()

            try:
                return our_response.wait_accept()
            except Exception:
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


class SingleUseActivityManager:
    def __init__(self, get_agreement: 'Callable'):
        self.get_agreement = get_agreement

    def get_activity(self) -> 'Activity':
        while True:
            # We need to release agreement if is not used
            agreement = self.get_agreement()
            try:
                return agreement.create_activity()
            except Exception:
                pass

    def apply_activity_decorators(self, func, work):
        if not hasattr(work, '_activity_decorators'):
            return func

        result = func
        for dec in work._activity_decorators:
            result = partial(dec, result)

        return result


    def do_work(self, work: 'Callable', on_activity_begin: 'Callable' = None, on_activity_end: 'Callable' = None) -> 'WorkResult':
        activity = self.get_activity()

        if on_activity_begin:
            activity.do(on_activity_begin)

        decorated_do = self.apply_activity_decorators(activity.do, work)

        try:
            return decorated_do(work)
        except Exception:
            pass

        if on_activity_end:
            activity.do(on_activity_end)

    def do_work_list(self, work_list: 'List[Callable]', on_activity_begin: 'Callable' = None, on_activity_end: 'Callable' = None) -> 'List[WorkResult]':
        results = []

        for work in work_list:
            results.append(
                self.do_work(work, on_activity_begin, on_activity_end)
            )

        return results


def blacklist_offers(blacklist: 'List'):
    def _blacklist_offers(func):
        def wrapper(*args, **kwargs):
            while True:
                offer = func()

                if offer not in blacklist:
                    return offer

        return wrapper

    return _blacklist_offers


def retry(tries: int = 3):
    def _retry(func):
        def wrapper(work) -> 'WorkResult':
            count = 0
            errors = []

            while count <= tries:
                try:
                    return func(work)
                except Exception as err:
                    count += 1
                    errors.append(err)

            raise errors  # List[Exception] to Exception

        return wrapper

    return _retry


def redundancy_cancel_others_on_first_done(size: int = 3):
    def _redundancy(func):
        def wrapper(work):
            tasks = [func(work) for _ in range(size)]

            task_done, tasks_in_progress = return_on_first_done(tasks)

            for task in tasks_in_progress:
                task.cancel()

            return task_done

        return wrapper

    return _redundancy


def default_on_begin(context):
    context.deploy()
    context.start()


def default_on_end(context):
    context.terminate()

    # After this function call we should have check for activity termination


def activity_decorator(dec, *args, **kwargs):
    def _activity_decorator(func):
        if not hasattr(func, '_activity_decorators'):
            func._activity_decorators = []

        func._activity_decorators.append(dec)

        return func

    return _activity_decorator


@activity_decorator(redundancy_cancel_others_on_first_done(size=5))
@activity_decorator(retry(tries=5))
def work(context):
    context.run('echo hello world')


async def work_service(context):
    context.run('app --daemon')


async def work_service_fetch(context):
    context.run('app --daemon &')

    while context.run('app check-if-running'):
        sleep(1)


async def work_batch(context):
    script = context.create_batch()
    script.add_run('echo 1')
    script.add_run('echo 2')
    script.add_run('echo 3')
    await script.run()


def main():
    payload = RepositoryVmPayload(image_url='...')
    budget = 1.0
    work_list = [
        work,
        work,
        work,
    ]
    event_bus = EventBus()

    payment_manager = PayAllPaymentManager(budget, event_bus)

    offer_manager = FifoOfferManager(payment_manager.get_allocation, event_bus)
    offer_manager.collect_proposals_for(payload)

    agreement_manager = FifoAgreementManager(
        blacklist_offers(['banned_node_id'])(offer_manager.get_offer)
    )

    activity_manager = SingleUseActivityManager(agreement_manager.get_agreement)
    activity_manager.do_work_list(
        work_list,
        on_activity_begin=default_on_begin,
        on_activity_end=default_on_end
    )
