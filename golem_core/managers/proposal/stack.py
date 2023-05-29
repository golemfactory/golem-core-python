import asyncio
import logging
from typing import List

from golem_core.core.market_api import Proposal
from golem_core.managers.base import ProposalAggregationManager

logger = logging.getLogger(__name__)


class StackProposalManager(ProposalAggregationManager):
    def __init__(self, get_proposal) -> None:
        self._get_proposal = get_proposal
        self._proposals: asyncio.Queue[Proposal] = asyncio.Queue()
        self._tasks: List[asyncio.Task] = []

    async def start_consuming_proposals(self) -> None:
        logger.debug("Starting manager")
        self._tasks.append(asyncio.create_task(self._consume_proposals()))

    async def stop_consuming_proposals(self) -> None:
        for task in self._tasks:
            logger.debug("Stopping manager")
            task.cancel()

    async def _consume_proposals(self) -> None:
        while True:
            proposal = await self._get_proposal()
            logger.debug("Adding proposal to the stack")
            await self._proposals.put(proposal)

    async def get_proposal(self) -> Proposal:
        proposal = await self._proposals.get()
        logger.debug("Returning proposal from the stack")
        return proposal
