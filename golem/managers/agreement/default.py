import logging
from typing import Awaitable, Callable

from golem.managers.base import AgreementManager
from golem.node import GolemNode
from golem.resources import ActivityClosed, Agreement, Proposal
from golem.utils.logging import trace_span

logger = logging.getLogger(__name__)


class DefaultAgreementManager(AgreementManager):
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

    @trace_span("Getting agreement", show_results=True, log_level=logging.INFO)
    async def get_agreement(self) -> Agreement:
        while True:
            proposal = await self._get_draft_proposal()
            try:
                agreement = await proposal.create_agreement()
                await agreement.confirm()
                await agreement.wait_for_approval()
            except Exception as e:
                logger.debug(f"Creating agreement failed with `{e}`. Retrying...")
            else:
                # TODO: Support removing callback on resource close
                await self._event_bus.on_once(
                    ActivityClosed,
                    self._terminate_agreement,
                    lambda event: event.resource.parent.id == agreement.id,
                )
                return agreement

    @trace_span(show_arguments=True)
    async def _terminate_agreement(self, event: ActivityClosed) -> None:
        # TODO ensure agreement it is terminated on SIGINT
        agreement: Agreement = event.resource.parent
        await agreement.terminate()
        logger.info(f"Agreement `{agreement}` closed")
