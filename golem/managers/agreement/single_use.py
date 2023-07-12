import logging
from typing import Awaitable, Callable

from golem.managers.agreement.events import AgreementReleased
from golem.managers.base import AgreementManager
from golem.node import GolemNode
from golem.resources import Agreement, Proposal
from golem.utils.logging import trace_span

logger = logging.getLogger(__name__)


class SingleUseAgreementManager(AgreementManager):
    def __init__(self, golem: GolemNode, get_proposal: Callable[[], Awaitable[Proposal]]):
        self._get_proposal = get_proposal
        self._event_bus = golem.event_bus

    @trace_span()
    async def get_agreement(self) -> Agreement:
        while True:
            proposal = await self._get_proposal()
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
    async def _terminate_agreement(self, event: AgreementReleased) -> None:
        agreement: Agreement = event.resource
        await agreement.terminate()
        logger.info(f"Agreement `{agreement}` closed")
