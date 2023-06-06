import asyncio
import logging
from typing import List

from golem_core.core.golem_node.golem_node import GolemNode
from golem_core.core.market_api import Proposal
from golem_core.managers.base import ProposalManager

logger = logging.getLogger(__name__)


class StackProposalManager(ProposalManager):
    def __init__(self, golem: GolemNode, get_proposal) -> None:
        self._get_proposal = get_proposal
        self._proposals: asyncio.Queue[Proposal] = asyncio.Queue()
        self._tasks: List[asyncio.Task] = []

    async def start(self) -> None:
        logger.debug("Starting...")

        self._tasks.append(asyncio.create_task(self._consume_proposals()))

        logger.debug("Starting done")

    async def stop(self) -> None:
        logger.debug("Stopping...")

        for task in self._tasks:
            task.cancel()

        logger.debug("Stopping done")

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
