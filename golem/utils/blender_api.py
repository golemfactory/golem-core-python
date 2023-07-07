from typing import List

from golem.managers.activity.pool import ActivityPoolManager
from golem.managers.agreement.single_use import SingleUseAgreementManager
from golem.managers.base import WorkResult
from golem.managers.negotiation import SequentialNegotiationManager
from golem.managers.negotiation.plugins import AddChosenPaymentPlatform
from golem.managers.payment.pay_all import PayAllPaymentManager
from golem.managers.proposal import StackProposalManager
from golem.managers.work.asynchronous import AsynchronousWorkManager
from golem.managers.work.plugins import retry
from golem.node import GolemNode


async def run_on_golem(
    task_list,
    payload,
    init_func,
    threads=6,
    budget=1.0,
    market_plugins=[
        AddChosenPaymentPlatform(),
    ],
    execution_plugins=[retry(tries=3)],
):
    golem = GolemNode()

    payment_manager = PayAllPaymentManager(golem, budget=budget)
    negotiation_manager = SequentialNegotiationManager(
        golem,
        payment_manager.get_allocation,
        payload,
        plugins=market_plugins,
    )
    proposal_manager = StackProposalManager(golem, negotiation_manager.get_proposal)
    agreement_manager = SingleUseAgreementManager(golem, proposal_manager.get_proposal)
    activity_manager = ActivityPoolManager(
        golem, agreement_manager.get_agreement, size=threads, on_activity_start=init_func
    )
    work_manager = AsynchronousWorkManager(
        golem, activity_manager.do_work, plugins=execution_plugins
    )

    async with golem, payment_manager, negotiation_manager, proposal_manager, activity_manager:
        results: List[WorkResult] = await work_manager.do_work_list(task_list)
    return results
