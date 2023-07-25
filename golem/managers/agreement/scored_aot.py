import logging
from datetime import timedelta
from typing import Awaitable, Callable, MutableSequence, Sequence, Tuple

from golem.managers.agreement.events import AgreementReleased
from golem.managers.base import AgreementManager
from golem.managers.mixins import WeightProposalScoringPluginsMixin
from golem.node import GolemNode
from golem.resources import Agreement, Proposal
from golem.utils.buffer import ConcurrentlyFilledBuffer
from golem.utils.logging import trace_span

logger = logging.getLogger(__name__)


class ScoredAheadOfTimeAgreementManager(WeightProposalScoringPluginsMixin, AgreementManager):
    def __init__(
        self,
        golem: GolemNode,
        get_draft_proposal: Callable[[], Awaitable[Proposal]],
        buffer_size: Tuple[int, int] = (1, 1),
        *args,
        **kwargs,
    ):
        self._get_draft_proposal = get_draft_proposal
        self._event_bus = golem.event_bus

        self._buffer = ConcurrentlyFilledBuffer(
            fill_callback=self._get_draft_proposal,
            min_size=buffer_size[0],
            max_size=buffer_size[1],
            update_callback=self._update_buffer_callback,
            update_interval=timedelta(seconds=2),
        )

        super().__init__(*args, **kwargs)

    @trace_span(show_arguments=True)
    async def get_agreement(self) -> Agreement:
        while True:
            proposal = await self._buffer.get_item()
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
                    self._terminate_agreement,
                    lambda event: event.resource.id == agreement.id,
                )
                return agreement

    @trace_span()
    async def start(self) -> None:
        await self._buffer.start()

    @trace_span()
    async def stop(self) -> None:
        await self._buffer.stop()

    @trace_span(show_arguments=True)
    async def _update_buffer_callback(
        self, items: MutableSequence[Proposal], items_to_process: Sequence[Proposal]
    ) -> None:
        scored_proposals = [
            proposal for _, proposal in await self.do_scoring([*items, *items_to_process])
        ]
        items.clear()
        items.extend(scored_proposals)

    @trace_span(show_arguments=True)
    async def _terminate_agreement(self, event: AgreementReleased) -> None:
        agreement: Agreement = event.resource
        await agreement.terminate()
        logger.info(f"Agreement `{agreement}` closed")
