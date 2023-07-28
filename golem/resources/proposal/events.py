from typing import TYPE_CHECKING

from golem.resources.events import NewResource, ResourceClosed, ResourceDataChanged

if TYPE_CHECKING:
    from golem.resources.proposal.proposal import Proposal  # noqa


class NewProposal(NewResource["Proposal"]):
    pass


class ProposalDataChanged(ResourceDataChanged["Proposal"]):
    pass


class ProposalClosed(ResourceClosed["Proposal"]):
    pass
