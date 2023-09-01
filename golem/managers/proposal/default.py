from typing import Awaitable, Callable, List, Optional, Sequence

from golem.managers.base import ProposalManager, ProposalManagerPlugin
from golem.managers.proposal.plugins.negotiating.negotiating_plugin import NegotiatingPlugin
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
        self._plugins: List[ProposalManagerPlugin] = (
            list(plugins) if plugins is not None else [NegotiatingPlugin()]
        )

    async def get_draft_proposal(self) -> Proposal:
        return await self._get_proposal_with_plugins()

    async def start(self) -> None:
        for p in self._plugins:
            p.set_proposal_callback(self._get_proposal_with_plugins)
            self._get_proposal_with_plugins = p.get_proposal
            await p.start()

    async def stop(self) -> None:
        for p in reversed(self._plugins):
            await p.stop()
