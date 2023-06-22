import asyncio
import logging
from typing import Optional

from golem_core.core.golem_node.golem_node import GolemNode
from golem_core.core.market_api import Proposal
from golem_core.managers.base import ManagerException, ProposalManager
from golem_core.utils.asyncio import create_task_with_logging

logger = logging.getLogger(__name__)


class StackProposalManager(ProposalManager):
    def __init__(self, golem: GolemNode, get_proposal) -> None:
        self._get_proposal = get_proposal
        self._proposals: asyncio.Queue[Proposal] = asyncio.Queue()
        self._consume_proposals_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        logger.debug("Starting...")

        if self.is_started():
            message = "Already started!"
            logger.debug(f"Starting failed with `{message}`")
            raise ManagerException(message)

        self._consume_proposals_task = create_task_with_logging(self._consume_proposals())

        logger.debug("Starting done")

    async def stop(self) -> None:
        logger.debug("Stopping...")

        if not self.is_started():
            message = "Already stopped!"
            logger.debug(f"Stopping failed with `{message}`")
            raise ManagerException(message)

        self._consume_proposals_task.cancel()
        self._consume_proposals_task = None

        logger.debug("Stopping done")

    def is_started(self) -> bool:
        return self._consume_proposals_task is not None and not self._consume_proposals_task.done()

    async def _consume_proposals(self) -> None:
        while True:
            proposal = await self._get_proposal()

            logger.debug(f"Adding proposal `{proposal}` on the stack")

            await self._proposals.put(proposal)

    async def get_proposal(self) -> Proposal:
        logger.debug("Getting proposal...")

        proposal = await self._proposals.get()

        logger.debug(f"Getting proposal done with `{proposal}`")

        logger.info(f"Proposal `{proposal}` picked")

        return proposal
