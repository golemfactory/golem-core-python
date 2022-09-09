import asyncio
from abc import ABC, ABCMeta
import re
from typing import AsyncIterator, Awaitable, Callable, Generic, List, Optional, TYPE_CHECKING, Type

from golem_api.events import NewResource, ResourceDataChanged
from golem_api.low.api_call_wrapper import api_call_wrapper
from golem_api.low.resource_internals import (
    get_requestor_api, ResourceType, RequestorApiType, ModelType, ParentType, ChildType, EventType
)

if TYPE_CHECKING:
    from golem_api import GolemNode


class ResourceMeta(ABCMeta):
    """Resources metaclass. Ensures a single instance per resource id. Emits the NewResource event."""

    def __call__(cls, node: "GolemNode", id_: str, *args, **kwargs):  # type: ignore
        assert isinstance(cls, type(Resource))  # mypy
        if args:
            #   Sanity check: when data is passed, it must be a new resource
            assert id_ not in node._resources[cls]

        if id_ not in node._resources[cls]:
            obj = super(ResourceMeta, cls).__call__(node, id_, *args, **kwargs)  # type: ignore
            node._resources[cls][id_] = obj
            node.event_bus.emit(NewResource(obj))
        return node._resources[cls][id_]


class Resource(
    ABC,
    Generic[RequestorApiType, ModelType, ParentType, ChildType, EventType],
    metaclass=ResourceMeta
):
    """Base class of all low-level objects.

    TODO - fix typing in the documentation of this class. I'm afraid this might require
    changes in `sphinx_autodoc_typehints`.

    TODO - in the final version this should disappear from the public docs and all these methods
    should be described on subclasses, but this doesn't make much sense before the previous TODO.
    """
    def __init__(self, node: "GolemNode", id_: str, data: Optional[ModelType] = None):
        self._node = node
        self._id = id_
        self._data: Optional[ModelType] = data

        self._parent: Optional[ParentType] = None
        self._children: List[ChildType] = []
        self._events: List[EventType] = []

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
    def parent(self) -> ParentType:
        """Returns a :class:`Resource` we are a child of. Details: :func:`children`."""
        assert self._parent is not None
        return self._parent

    def add_child(self, child: ChildType) -> None:
        assert child._parent is None  # type:ignore
        child._parent = self  # type: ignore
        self._children.append(child)

    @property
    def children(self) -> List[ChildType]:
        """List of Resources that were created "from" this resource.

        E.g. children of a :any:`Demand` are :any:`Proposal`.
        Children of :any:`Proposal` are either :any:`Proposal` (counter-proposals to it),
        or :any:`Agreement`.

        """
        return self._children.copy()

    async def child_aiter(self) -> AsyncIterator[ChildType]:
        """Yields children. Stops when :class:`Resource` knows there will be no more children."""
        async def no_more_children() -> None:  # type: ignore  # missing return statement?
            await self._no_more_children

        stop_task = asyncio.create_task(no_more_children())

        cnt = 0
        while True:
            if cnt < len(self._children):
                yield self._children[cnt]
                cnt += 1
            else:
                #   TODO: make this more efficient (remove sleep)
                #         (e.g. by setting some awaitable to done in add_child)
                wait_task: asyncio.Task = asyncio.create_task(asyncio.sleep(0.1))
                await asyncio.wait((wait_task, stop_task), return_when=asyncio.FIRST_COMPLETED)
                if stop_task.done():
                    wait_task.cancel()
                    break

    def add_event(self, event: EventType) -> None:
        self._events.append(event)

    @property
    def events(self) -> List[EventType]:
        """Returns a list of all `yagna` events related to this :class:`Resource`.

        Note: these are **yagna** events and should not be confused with `golem_api.events`.
        """
        return self._events.copy()

    def set_no_more_children(self) -> None:
        """This resource will have no more children. This stops :any:`child_aiter` iterator.

        This can be called either from iside the resource (e.g. Proposal sets this when it receives
        a ProposalRejected event), or from outside (e.g. on shutdown).
        """
        if not self._no_more_children.done():
            self._no_more_children.set_result(None)

    ####################
    #   PROPERTIES
    @property
    def api(self) -> RequestorApiType:
        return self._get_api(self.node)

    @property
    def id(self) -> str:
        """Id of the resource, generated by `yagna`."""
        return self._id

    @property
    def data(self) -> ModelType:
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
        """:any:`GolemNode` that defines the context of this :class:`Resource`"""
        return self._node

    ####################
    #   DATA LOADING
    async def get_data(self, force: bool = False) -> ModelType:
        """Returns details of this resource.

        :param force: False -> returns the cached data (or fetches data from `yagna` if there is no cached version).
            True -> always fetches the new data (and updates the cache).

        """
        async with self._get_data_lock:
            if self._data is None or force:
                old_data = self._data
                self._data = await self._get_data()
                if old_data != self._data:
                    self.node.event_bus.emit(ResourceDataChanged(self, old_data))

        assert self._data is not None  # mypy
        return self._data

    @api_call_wrapper()
    async def _get_data(self) -> ModelType:
        get_method: Callable[[str], Awaitable[ModelType]] = getattr(self.api, self._get_method_name)
        return await get_method(self._id)

    @classmethod
    @api_call_wrapper()
    async def get_all(cls: Type[ResourceType], node: "GolemNode") -> List[ResourceType]:
        api = cls._get_api(node)
        get_all_method = getattr(api, cls._get_all_method_name())
        data = await get_all_method()

        resources = []
        id_field = f'{cls.__name__.lower()}_id'
        for raw in data:
            id_ = getattr(raw, id_field)
            resources.append(cls(node, id_, raw))
        return resources

    ###################
    #   OTHER
    @classmethod
    def _get_api(cls, node: "GolemNode") -> RequestorApiType:
        return get_requestor_api(cls, node)  # type: ignore

    @property
    def _get_method_name(self) -> str:
        """Name of the single GET ya_client method, e.g. get_allocation."""
        snake_case_name = re.sub('([A-Z]+)', r'_\1', type(self).__name__).lower()
        return f'get' + snake_case_name

    @classmethod
    def _get_all_method_name(cls) -> str:
        """Name of the collection GET ya_client method, e.g. get_allocations."""
        return f'get_{cls.__name__.lower()}s'

    def __str__(self) -> str:
        return f'{type(self).__name__}({self._id})'
