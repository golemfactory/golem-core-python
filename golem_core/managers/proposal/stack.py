import asyncio
import logging
from typing import List

from golem_core.core.golem_node.golem_node import GolemNode
from golem_core.core.market_api import Proposal
from golem_core.managers.base import ProposalAggregationManager

logger = logging.getLogger(__name__)


class StackProposalManager(ProposalAggregationManager):
    def __init__(self, golem: GolemNode, get_proposal) -> None:
        self._get_proposal = get_proposal
        self._proposals: asyncio.Queue[Proposal] = asyncio.Queue()
        self._tasks: List[asyncio.Task] = []

    async def start_consuming_proposals(self) -> None:
        logger.debug("Starting consuming proposals...")
        self._tasks.append(asyncio.create_task(self._consume_proposals()))
        logger.debug("Starting consuming proposals done")

    async def stop_consuming_proposals(self) -> None:
        logger.debug("Stopping consuming proposals...")
        for task in self._tasks:
            task.cancel()
        logger.debug("Stopping consuming proposals done")

    async def _consume_proposals(self) -> None:
        while True:
            proposal = await self._get_proposal()
            logger.debug("Adding proposal to the stack")
            await self._proposals.put(proposal)

    async def get_proposal(self) -> Proposal:
        logger.info("Getting proposals...")
        proposal = await self._proposals.get()
        logger.info("Getting proposals done")
        return proposal
