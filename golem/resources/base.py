import asyncio
import re
from abc import ABC, ABCMeta
from functools import wraps
from typing import (
    TYPE_CHECKING,
    AsyncIterator,
    Awaitable,
    Callable,
    Generic,
    List,
    Optional,
    Type,
    TypeVar,
)

from typing_extensions import ParamSpec
from ya_activity import ApiException as ActivityApiException
from ya_market import ApiException as MarketApiException
from ya_net import ApiException as NetApiException
from ya_payment import ApiException as PaymentApiException

from golem.resources.events import ResourceDataChanged
from golem.resources.exceptions import ResourceNotFound
from golem.utils.low import TRequestorApi, get_requestor_api

if TYPE_CHECKING:
    from golem.node import GolemNode

all_api_exceptions = (
    PaymentApiException,
    MarketApiException,
    ActivityApiException,
    NetApiException,
)
P = ParamSpec("P")
R = TypeVar("R")

TResource = TypeVar("TResource", bound="Resource")
TModel = TypeVar("TModel")
TParent = TypeVar("TParent")
TChild = TypeVar("TChild")
TEvent = TypeVar("TEvent")


class _NULL:
    """Set this as a type to tell the typechecker that call is just invalid.

    This might be ugly, but keeps Resource inheritance tree simple.
    """


def api_call_wrapper(
    ignore: List[int] = [],
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    def outer_wrapper(f: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @wraps(f)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Optional[R]:
            try:
                return await f(*args, **kwargs)
            except all_api_exceptions as e:
                if e.status in ignore:
                    return None
                elif e.status == 404:
                    self = args[0]
                    raise ResourceNotFound(self)  # type: ignore
                else:
                    raise

        return wrapper  # type: ignore  # I don't understand this :/

    return outer_wrapper


class ResourceMeta(ABCMeta):
    """Resources metaclass.

    Ensures a single instance per resource id. Emits the NewResource event.
    """

    def __call__(cls, node: "GolemNode", id_: str, *args, **kwargs):
        assert isinstance(cls, type(Resource))  # mypy
        if args:
            #   Sanity check: when data is passed, it must be a new resource
            assert id_ not in node._resources[cls], f"Repeated id {id_} for class {cls.__name__}"

        if id_ not in node._resources[cls]:
            obj = super(ResourceMeta, cls).__call__(node, id_, *args, **kwargs)  # type: ignore
            node._resources[cls][id_] = obj

            # FIXME: Is there any better solution for this?
            # asyncio.create_task(node.event_bus.emit(NewResource(obj)))

        return node._resources[cls][id_]


class Resource(
    ABC, Generic[TRequestorApi, TModel, TParent, TChild, TEvent], metaclass=ResourceMeta
):
    """Base class of all core-level objects.

    TODO - fix typing in the documentation of this class. I'm afraid this might require
    changes in `sphinx_autodoc_typehints`.

    TODO - in the final version this should disappear from the public docs and all these methods
    should be described on subclasses, but this doesn't make much sense before the previous TODO.
    Related issue: https://github.com/golemfactory/golem-core-python/issues/26
    """

    def __init__(self, node: "GolemNode", id_: str, data: Optional[TModel] = None):
        self._node = node
        self._id = id_
        self._data: Optional[TModel] = data

        self._parent: Optional[TParent] = None
        self._children: List[TChild] = []
        self._events: List[TEvent] = []

        #   When this is done, we know self._children will never change again
        #   This is set by particular resources depending on their internal logic,
        #   and consumed in Resource.child_aiter().
        self._no_more_children: asyncio.Future = asyncio.Future()

        #   Lock for Resource.get_data calls. We don't want to update the same Resource in
        #   multiple tasks at the same time.
        self._get_data_lock = asyncio.Lock()

    ################################
    #   RESOURCE TREE & YAGNA EVENTS
    @property
    def parent(self) -> TParent:
        """Returns a :class:`Resource` we are a child of. Details: :func:`children`."""
        assert self._parent is not None, f"Parent of {self} is not set"
        return self._parent

    @property
    def has_parent(self) -> bool:
        return self._parent is not None

    def add_child(self, child: TChild) -> None:
        assert child._parent is None  # type:ignore
        child._parent = self  # type: ignore
        self._children.append(child)

    @property
    def children(self) -> List[TChild]:
        """List of Resources that were created "from" this resource.

        E.g. children of a :any:`Demand` are :any:`Proposal`.
        Children of :any:`Proposal` are either :any:`Proposal` (counter-proposals to it),
        or :any:`Agreement`.

        """
        return self._children.copy()

    async def child_aiter(self) -> AsyncIterator[TChild]:
        """Yield children. Stops when :class:`Resource` knows there will be no more children."""

        async def no_more_children() -> None:  # missing return statement?
            await self._no_more_children

        stop_task = asyncio.create_task(no_more_children())

        cnt = 0
        while True:
            if cnt < len(self._children):
                yield self._children[cnt]
                cnt += 1
            else:
                #   TODO: https://github.com/golemfactory/golem-core-python/issues/36
                wait_task: asyncio.Task = asyncio.create_task(asyncio.sleep(0.1))
                await asyncio.wait((wait_task, stop_task), return_when=asyncio.FIRST_COMPLETED)
                if stop_task.done():
                    wait_task.cancel()
                    stop_task.result()
                    break

    def add_event(self, event: TEvent) -> None:
        self._events.append(event)

    @property
    def events(self) -> List[TEvent]:
        """Returns a list of all `yagna` events related to this :class:`Resource`.

        Note: these are **yagna** events and should not be confused with `golem.resources.events`.
        """
        return self._events.copy()

    def set_no_more_children(self, exception: Optional[Exception] = None) -> None:
        """Stop :any:`child_aiter` iterator marking as this resource will have no more children.

        This can be called either from iside the resource (e.g. Proposal sets this when it receives
        a ProposalRejected event), or from outside (e.g. on shutdown).
        """
        if not self._no_more_children.done():
            if exception:
                self._no_more_children.set_exception(exception)
            else:
                self._no_more_children.set_result(None)

    ####################
    #   PROPERTIES
    @property
    def api(self) -> TRequestorApi:
        return self._get_api(self.node)

    @property
    def id(self) -> str:
        """Id of the resource, generated by `yagna`."""
        return self._id

    @property
    def data(self) -> TModel:
        """Same as :func:`get_data`, but cached.

        Raises :class:`RuntimeError` if data was never fetched.

        NOTE: `data` might be available even without a prior call to :func:`get_data`
        because some resources (e.g. initial :any:`Proposal`) are fetched from `yagna`
        with full data right away.
        """
        if self._data is None:
            raise RuntimeError(f"Unknown {type(self).__name__} data - call get_data() first")
        return self._data

    @property
    def node(self) -> "GolemNode":
        """:any:`GolemNode` that defines the context of this :class:`Resource`."""
        return self._node

    ####################
    #   DATA LOADING
    async def get_data(self, force: bool = False) -> TModel:
        """Return details of this resource.

        :param force: False -> returns the cached data (or fetches data from `yagna` if there is no
            cached version). True -> always fetches the new data (and updates the cache).

        """
        async with self._get_data_lock:
            if self._data is None or force:
                old_data = self._data
                self._data = await self._get_data()
                if old_data is not None and old_data != self._data:
                    await self.node.event_bus.emit(ResourceDataChanged(self, old_data))

        assert self._data is not None  # mypy
        return self._data

    @api_call_wrapper()
    async def _get_data(self) -> TModel:
        get_method: Callable[[str], Awaitable[TModel]] = getattr(self.api, self._get_method_name)
        return await get_method(self._id)

    @classmethod
    @api_call_wrapper()
    async def get_all(cls: Type[TResource], node: "GolemNode") -> List[TResource]:
        api = cls._get_api(node)
        get_all_method = getattr(api, cls._get_all_method_name())
        data = await get_all_method()

        resources = []
        id_field = cls._id_field_name()
        for raw in data:
            id_ = getattr(raw, id_field)
            resources.append(cls(node, id_, raw))
        return resources

    ###################
    #   OTHER
    @classmethod
    def _get_api(cls, node: "GolemNode") -> TRequestorApi:
        return get_requestor_api(cls, node)

    @property
    def _get_method_name(self) -> str:
        """Name of the single GET ya_client method, e.g. get_allocation."""
        return f"get_{self._snake_case_name()}"

    @classmethod
    def _get_all_method_name(cls) -> str:
        """Name of the collection GET ya_client method, e.g. get_allocations."""
        return f"get_{cls._snake_case_name()}s"

    @classmethod
    def _id_field_name(cls) -> str:
        return f"{cls._snake_case_name()}_id"

    @classmethod
    def _snake_case_name(cls) -> str:
        replaced = re.sub("([A-Z]+)", r"_\1", cls.__name__).lower()
        return replaced[1:]

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._id})"
