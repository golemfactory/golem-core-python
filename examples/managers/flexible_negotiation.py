import asyncio
import logging.config

from golem.managers import (
    AutoDemandManager,
    PayAllPaymentManager,
    SequentialWorkManager,
    WorkContext,
    WorkResult,
)
from golem.managers.activity.pool import ActivityPoolManager
from golem.managers.agreement.scored_aot import ScoredAheadOfTimeAgreementManager
from golem.managers.negotiation.plugins import AddChosenPaymentPlatform
from golem.managers.proposal.default import DefaultProposalManager
from golem.managers.proposal.plugins import BlacklistProviderId, NegotiateProposal
from golem.node import GolemNode
from golem.payload import RepositoryVmPayload
from golem.utils.logging import DEFAULT_LOGGING

BLACKLISTED_PROVIDERS = [
    "0x3b0f605fcb0690458064c10346af0c5f6b7202a5",
    "0x7ad8ce2f95f69be197d136e308303d2395e68379",
    "0x40f401ead13eabe677324bf50605c68caabb22c7",
]


async def commands_work_example(context: WorkContext) -> str:
    r = await context.run("echo 'hello golem'")
    await r.wait()
    result = ""
    for event in r.events:
        result += event.stdout
    return result


async def main():
    logging.config.dictConfig(DEFAULT_LOGGING)
    payload = RepositoryVmPayload("9a3b5d67b0b27746283cb5f287c13eab1beaa12d92a9f536b747c7ae")

    golem = GolemNode()

    payment_manager = PayAllPaymentManager(golem, budget=1.0)
    # demand_manager without scoring
    demand_manager = AutoDemandManager(golem, payment_manager.get_allocation, payload)

    proposal_manager = DefaultProposalManager(
        golem,
        demand_manager.get_initial_proposal,
        plugins=[
            BlacklistProviderId(BLACKLISTED_PROVIDERS),
            NegotiateProposal(plugins=[AddChosenPaymentPlatform()]),
        ],
    )

    # PluginManager(callback, plugins*)
    # negoatiation_plugin_manager = PluginManager(
    #     demand_manager.get_proposal,
    #     Blacklist(),
    #     MostPromising(),
    #     AddChosenPaymentPlatform(),
    #     Negotiate(),
    #     OrderByPrice(),
    # )

    # agreement_manager without scoring
    agreement_manager = ScoredAheadOfTimeAgreementManager(
        golem, proposal_manager.get_draft_proposal
    )
    activity_manager = ActivityPoolManager(golem, agreement_manager.get_agreement, size=3)
    work_manager = SequentialWorkManager(golem, activity_manager.do_work)

    async with golem:
        async with payment_manager, demand_manager, proposal_manager, agreement_manager, activity_manager:  # noqa: E501 line too long
            await asyncio.sleep(20)
            results: WorkResult = await work_manager.do_work(commands_work_example)
            print(f"\nWORK MANAGER RESULT:{results}\n")


if __name__ == "__main__":
    asyncio.run(main())
