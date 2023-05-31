import logging
from typing import Awaitable, Callable

from golem_core.core.golem_node.golem_node import GolemNode
from golem_core.core.market_api import Agreement, Proposal
from golem_core.managers.agreement.events import AgreementReleased
from golem_core.managers.base import AgreementManager

logger = logging.getLogger(__name__)


class SingleUseAgreementManager(AgreementManager):
    def __init__(self, golem: GolemNode, get_proposal: Callable[[], Awaitable[Proposal]]):
        self._get_proposal = get_proposal
        self._event_bus = golem.event_bus

    async def get_agreement(self) -> Agreement:
        logger.info("Getting agreement...")

        while True:
            logger.debug("Getting proposal...")

            proposal = await self._get_proposal()

            logger.debug(f"Getting proposal done with {proposal}")

            try:
                logger.info("Creating agreement...")

                agreement = await proposal.create_agreement()

                logger.debug("Sending agreement to provider...")

                await agreement.confirm()

                logger.debug("Waiting for provider approval...")

                await agreement.wait_for_approval()
            except Exception as e:
                logger.debug(f"Creating agreement failed with {e}. Retrying...")
            else:
                logger.info(f"Creating agreement done {agreement.id}")

                # TODO: Support removing callback on resource close
                self._event_bus.resource_listen(
                    self._on_agreement_released, [AgreementReleased], [Agreement], [agreement.id]
                )

                logger.info(f"Getting agreement done  {agreement.id}")
                return agreement

    async def _on_agreement_released(self, event: AgreementReleased) -> None:
        logger.debug("Calling `_on_agreement_released`...")

        agreement: Agreement = event.resource
        await agreement.terminate()

        logger.debug("Calling `_on_agreement_released` done")
