from golem_core.core.resources import NewResource, ResourceClosed, ResourceDataChanged


class NewDemand(NewResource["Demand"]):
    pass


class DemandDataChanged(ResourceDataChanged["Demand"]):
    pass


class DemandClosed(ResourceClosed["Demand"]):
    pass


class NewAgreement(NewResource["Agreement"]):
    pass


class AgreementDataChanged(ResourceDataChanged["Agreement"]):
    pass


class AgreementClosed(ResourceClosed["Agreement"]):
    pass


class NewProposal(NewResource["Proposal"]):
    pass


class ProposalDataChanged(ResourceDataChanged["Proposal"]):
    pass


class ProposalClosed(ResourceClosed["Proposal"]):
    pass
