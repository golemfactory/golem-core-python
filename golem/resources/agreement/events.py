class NewAgreement(NewResource["Agreement"]):
    pass


class AgreementDataChanged(ResourceDataChanged["Agreement"]):
    pass


class AgreementClosed(ResourceClosed["Agreement"]):
    pass
