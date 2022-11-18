"""The only purpose of this file is to increase code readability by separating "deep" internals
from the "important" part od the app logic"""

from typing import get_args, no_type_check, Any, Type, TypeVar, TYPE_CHECKING, Union

from ya_payment import models as payment_models, RequestorApi as PaymentApi
from ya_market import models as market_models, RequestorApi as MarketApi
from ya_activity import (
    ApiClient as ActivityApiClient,
    RequestorControlApi,
    RequestorStateApi,
    models as activity_models
)
from ya_net import models as net_models, RequestorApi as NetworkApi

if TYPE_CHECKING:
    from golem_api import GolemNode
    from golem_api.low.resource import Resource
    from golem_api.low import market, activity, network


class ActivityApi:
    """The purpose of this class is to have a single ActivityApi, just like Payment/Demand/Network,
    without "estetic" split to Control/State.

    Q: Why?
    A: Because we want to keep internal interface as unified as possible, at least for now -
       - we might want to change this in the future.
    """
    def __init__(self, ya_activity_api: ActivityApiClient):
        self.__control_api = RequestorControlApi(ya_activity_api)
        self.__state_api = RequestorStateApi(ya_activity_api)

    def __getattr__(self, attr_name: str) -> Any:
        try:
            return getattr(self.__control_api, attr_name)
        except AttributeError:
            return getattr(self.__state_api, attr_name)


#########################
#   TYPING BLACK MAGIC
class _NULL:
    """Set this as a type to tell the typechecker that call is just invalid.

    This might be ugly, but keeps Resource inheritance tree simple."""


ResourceType = TypeVar("ResourceType", bound="Resource")
RequestorApiType = TypeVar("RequestorApiType", PaymentApi, MarketApi, ActivityApi, NetworkApi)
ModelType = TypeVar(
    "ModelType",
    _NULL,
    payment_models.Allocation,
    payment_models.DebitNote,
    payment_models.Invoice,
    market_models.Demand,
    market_models.Proposal,
    market_models.Agreement,
    net_models.Network,
)
ParentType = TypeVar(
    "ParentType",
    _NULL,
    "market.Proposal",
    "market.Agreement",
    "activity.Activity",
    Union["market.Demand", "market.Proposal"],
    "network.Network",
)
ChildType = TypeVar(
    "ChildType",
    _NULL,
    "market.Proposal",
    "activity.Activity",
    "activity.PoolingBatch",
    Union["market.Proposal", "market.Agreement"],
)
EventType = TypeVar(
    "EventType",
    _NULL,
    Union[market_models.ProposalEvent, market_models.ProposalRejectedEvent],
    activity_models.ExeScriptCommandResult,
)


@no_type_check
def get_requestor_api(cls: Type["Resource"], node: "GolemNode") -> RequestorApiType:
    """Return RequestorApi for a given cls, using class typing.

    This is very ugly, but should work well and simplifies the Resource inheritance.
    If we ever decide this is too ugly, it shouldn"t be hard to get rid of this.

    NOTE: this references only "internal" typing, so is invisible from the interface POV.
    """
    api_type = get_args(cls.__orig_bases__[0])[0]
    if api_type is PaymentApi:
        api = PaymentApi(node._ya_payment_api)
        return api
    elif api_type is MarketApi:
        return MarketApi(node._ya_market_api)
    elif api_type is ActivityApi:
        return ActivityApi(node._ya_activity_api)
    elif api_type is NetworkApi:
        return NetworkApi(node._ya_net_api)
    raise TypeError("This should never happen")
