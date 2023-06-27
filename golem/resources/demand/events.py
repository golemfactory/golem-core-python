class NewDemand(NewResource["Demand"]):
    pass


class DemandDataChanged(ResourceDataChanged["Demand"]):
    pass


class DemandClosed(ResourceClosed["Demand"]):
    pass
