import logging
from typing import Awaitable, Callable

from golem.managers.agreement.events import AgreementReleased
from golem.managers.base import AgreementManager
from golem.managers.mixins import BackgroundLoopMixin, WeightProposalScoringPluginsMixin
from golem.node import GolemNode
from golem.resources import Agreement, Proposal
from golem.utils.logging import trace_span

logger = logging.getLogger(__name__)


class ScoredAheadOfTimeAgreementManager(
    BackgroundLoopMixin, WeightProposalScoringPluginsMixin, AgreementManager
):
    def __init__(
        self,
        golem: GolemNode,
        get_draft_proposal: Callable[[], Awaitable[Proposal]],
        *args,
        **kwargs,
    ):
        self._get_draft_proposal = get_draft_proposal
        self._event_bus = golem.event_bus

        super().__init__(*args, **kwargs)

    @trace_span(show_arguments=True)
    async def get_agreement(self) -> Agreement:
        while True:
            proposal = await self.get_scored_proposal()
            try:
                agreement = await proposal.create_agreement()
                await agreement.confirm()
                await agreement.wait_for_approval()
            except Exception as e:
                logger.debug(f"Creating agreement failed with `{e}`. Retrying...")
            else:
                logger.info(f"Agreement `{agreement}` created")

                # TODO: Support removing callback on resource close
                await self._event_bus.on_once(
                    AgreementReleased,
                    self._terminate_agreement_if_released,
                    lambda event: event.resource.id == agreement.id,
                )
                return agreement

    async def _background_loop(self) -> None:
        while True:
            proposal = await self._get_draft_proposal()

            await self.manage_scoring(proposal)

    @trace_span(show_arguments=True)
    async def _terminate_agreement(self, event: AgreementReleased) -> None:
        agreement: Agreement = event.resource
        await agreement.terminate()
        logger.info(f"Agreement `{agreement}` closed")
