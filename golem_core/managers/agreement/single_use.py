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
        logger.debug("Getting agreement...")

        while True:
            logger.debug("Getting proposal...")

            proposal = await self._get_proposal()

            logger.debug(f"Getting proposal done with {proposal}")

            try:
                logger.debug("Creating agreement...")

                agreement = await proposal.create_agreement()

                logger.debug("Sending agreement to provider...")

                await agreement.confirm()

                logger.debug("Waiting for provider approval...")

                await agreement.wait_for_approval()
            except Exception as e:
                logger.debug(f"Creating agreement failed with `{e}`. Retrying...")
            else:
                logger.debug(f"Creating agreement done with `{agreement}`")
                logger.info(f"Agreement `{agreement}` created")

                # TODO: Support removing callback on resource close
                await self._event_bus.on_once(
                    AgreementReleased,
                    self._terminate_agreement,
                    lambda e: e.resource.id == agreement.id,
                )

                logger.debug(f"Getting agreement done with `{agreement}`")

                return agreement

    async def _terminate_agreement(self, event: AgreementReleased) -> None:
        logger.debug("Calling `_terminate_agreement`...")

        agreement: Agreement = event.resource
        await agreement.terminate()

        logger.debug("Calling `_terminate_agreement` done")

        logger.info(f"Agreement `{agreement}` closed")
