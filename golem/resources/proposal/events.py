from golem.resources.resources import NewResource, ResourceClosed, ResourceDataChanged


class NewProposal(NewResource["Proposal"]):
    pass


class ProposalDataChanged(ResourceDataChanged["Proposal"]):
    pass


class ProposalClosed(ResourceClosed["Proposal"]):
    pass
