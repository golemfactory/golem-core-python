class PayAllPaymentManager:
    def __init__(self, budget, event_bus):
        self._budget = budget
        self._event_bus = event_bus

        self._allocation = Allocation.create(budget=self._budget)

        event_bus.register('InvoiceReceived', self.on_invoice_received)
        event_bus.register('DebitNoteReceived', self.on_debit_note_received)

    def get_allocation(self) -> 'Allocation':
        return self._allocation

    def on_invoice_received(self, invoice: 'Invoice') -> None:
        invoice.pay()

    def on_debit_note_received(self, debit_note: 'DebitNote') -> None:
        debit_note.pay()


class FifoOfferManager:
    def __init__(self, get_allocation: 'Callable'):
        self._proposals = []
        self.get_allocation = get_allocation

    def collect_proposals_for(self, payload) -> None:
        allocation = self.get_allocation()

        demand_builder = DemandBuilder()
        demand_builder.add(payload)
        demand_builder.add(allocation)
        demand = demand_builder.create_demand()
        self._proposals = demand.initial_proposals()
        demand.on_new_proposal(self.on_new_proposal)

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


class PooledActivityManager:
    def __init__(self, get_agreement: 'Callable', pool_size: int):
        self.get_agreement = get_agreement
        self._pool_size = pool_size

        self.activities = []

    def get_activity(self) -> 'Activity':
        while True:
            # We need to release agreement if is not used
            agreement = self.get_agreement()
            try:
                return agreement.create_activity()
            except Exception:
                pass

    def do_work(self, tasks: 'Iterable', before_all=None, after_all=None) -> None:
        activities = [self.get_activity() for _ in range(self._pool_size)]


        if before_all:
            activity.do(before_all)

        for task in tasks:
            try:
                activity.do(task)
            except Exception:
                pass

        if after_all:
            activity.do(after_all)


def blacklist_wrapper(get_offer, blacklist):
    def wrapper(*args, **kwargs):
        while True:
            offer = get_offer()

            if offer in blacklist:
                continue

            return offer

    return wrapper

def restart_wrapper():
    pass


def redundance_wrapper():
    pass


def default_before_all(context):
    context.deploy()
    context.start()


def work(context):
    context.run('echo hello world')


async def work_service(context):
    context.run('app start deamon')

    while context.run('app check-if-running'):
        sleep(1)


def default_after_all(context):
    context.terminate()


def main():
    payload = RepositoryVmPayload(image_url='...')
    budget = 1.0
    task_list = [
        work,
    ]

    payment_manager = PayAllPaymentManager(budget)
    offer_manager = FifoOfferManager(payment_manager.get_allocation)
    offer_manager.collect_proposals_for(payload)
    agreement_manager = FifoAgreementManager(
        blacklist_wrapper(offer_manager.get_offer, ['banned_node_id'])
    )
    activity_manager = PooledActivityManager(agreement_manager.get_agreement, pool_size=5)
    activity_manager.do_work(
        task_list,
        before_all=default_before_all,
        after_all=default_after_all
    )

    # Activity per task
    for task in task_list:
        with activity_manager.activity() as ctx:
            default_before_all()
            ctx.run(task)
            default_after_all()

    # Single activity
    with activity_manager.activity_context(
        before_all=default_before_all,
        after_all=default_after_all
    ) as ctx:
        for task in task_list:
            ctx.run(task)

    #Activity pool
    def pool_work(ctx):
        for task in task_list:
            yield ctx.run(task)

    activity_manager.activity_pool(
        before_all_per_activity=default_before_all,
        after_all_per_activity=default_after_all,
        work=pool_work,
    )

    def activity_context():
        activity = self.get_activity()
        if before_all:
            activity.do(before_all)

        yield activity

        if after_all:
            activity.do(after_all)

    def retry_failed_task_in_new_activity_plugin(get_task: 'Callable', retry_count_per_task: int):
        activity = get_activity()
        activity.before_all()
        task = get_task()
        tries = retry_count_per_task
        while True:
            try:
                activity.do(task)
            except Exception as e:
                if not retry_count_per_task:
                    raise Exception('Number of tries exceeded!') from e

                retry_count_per_task -= 1
                activity.after_all()
                activity = get_activity()
                activity.before_all()
            else:
                task = get_task()
                tries = retry_count_per_task

        activity.after_all()

    def redundance(get_task: 'Callable', redundance_size: int):
        task = get_task()

        activities = [get_activity() for _ in range(redundance_size)]
        for activity in activities:
            activity.before_all()
