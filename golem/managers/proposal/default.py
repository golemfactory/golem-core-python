from typing import Awaitable, Callable, List, Optional, Sequence

from golem.managers.base import ProposalManager, ProposalManagerPlugin
from golem.node.node import GolemNode
from golem.resources import Proposal


class DefaultProposalManager(ProposalManager):
    def __init__(
        self,
        golem: GolemNode,
        get_initial_proposal: Callable[[], Awaitable[Proposal]],
        plugins: Optional[Sequence[ProposalManagerPlugin]] = None,
    ) -> None:
        self._golem = golem
        self._get_initial_proposal = get_initial_proposal
        self._get_proposal_with_plugins = self._get_initial_proposal
        # TODO add deafult negotiation plugin
        self._plugins: List[ProposalManagerPlugin] = list(plugins) if plugins is not None else []

    async def get_draft_proposal(self) -> Proposal:
        return await self._get_proposal_with_plugins()

    async def start(self) -> None:
        for p in self._plugins:
            p.set_callback(self._get_proposal_with_plugins)
            self._get_proposal_with_plugins = p.get_proposal
            await p.start()

    async def stop(self) -> None:
        for p in self._plugins[::-1]:
            await p.stop()
