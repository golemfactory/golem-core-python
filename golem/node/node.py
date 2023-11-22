import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, DefaultDict, Dict, Iterable, List, Optional, Set, Type, Union
from uuid import uuid4

from golem.event_bus import EventBus
from golem.event_bus.in_memory import InMemoryEventBus
from golem.node.events import SessionStarted, ShutdownFinished, ShutdownStarted
from golem.payload import Payload
from golem.payload import defaults as payload_defaults
from golem.resources import (
    Activity,
    Agreement,
    Allocation,
    DebitNote,
    DebitNoteEventCollector,
    Demand,
    DemandBuilder,
    Invoice,
    InvoiceEventCollector,
    Network,
    PoolingBatch,
    Proposal,
    Resource,
    TResource,
)
from golem.utils.low import ApiConfig, ApiFactory


class _RandomSessionId:
    pass


class GolemNode:
    """Main entrypoint to the python Golem API, communicates with `yagna`.

    GolemNode object corresponds to a single identity and a single running `yagna` instance
    (--> it's identified by a (APPKEY, YAGNA_URL) pair) and can operate on different
    subnets / networks. Multiple GolemNode instances can be used to access different
    identities / `yagna` instances.

    Usage::

        golem = GolemNode()
        async with golem:
            #   Interact with the Golem Network

    """

    def __init__(
        self,
        app_key: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        collect_payment_events: bool = True,
        app_session_id: Optional[Union[str, Type[_RandomSessionId]]] = _RandomSessionId,
    ):
        """Init GolemNode.

        :param app_key: App key used as an authentication token for all `yagna` calls.
                        Defaults to the `YAGNA_APPKEY` env variable.
        :param base_url: Base url for all `yagna` APIs. Defaults to `YAGNA_API_URL` env
                         variable or http://127.0.0.1:7465.
        :param collect_payment_events: If True, GolemNode will watch for incoming
            debit notes/invoices and create corresponding objects (--> :any:`NewResource` events
            will be emitted).
        :param app_session_id: A correlation/session identifier. :any:`GolemNode` objects with the
            same `app_session_id` will receive the same debit note/invoice/agreement events.
            Defaults to a random sting. If set to `None`, this GolemNode will receive all events
            regardless of their corresponding session ids.
        """
        config_kwargs = {
            param: value
            for param, value in {"app_key": app_key, "base_url": base_url}.items()
            if value is not None
        }
        self._api_config = ApiConfig(**config_kwargs)
        self._collect_payment_events = collect_payment_events
        self.app_session_id = uuid4().hex if app_session_id is _RandomSessionId else app_session_id

        #   All created Resources will be stored here
        #   (This is done internally by the metaclass of the Resource)
        self._resources: DefaultDict[Type[Resource], Dict[str, Resource]] = defaultdict(dict)
        self._autoclose_resources: Set[Resource] = set()
        self._event_bus = InMemoryEventBus()

        self._invoice_event_collector = InvoiceEventCollector(self)
        self._debit_note_event_collector = DebitNoteEventCollector(self)

    @property
    def app_key(self) -> str:
        return self._api_config.app_key

    ########################
    #   Start/stop interface
    async def __aenter__(self) -> "GolemNode":
        """Start. Initialize all the APIs and the event bus."""
        await self.start()
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        """Shutdown.

        Stop collecting yagna events, close all resources created with autoclose=True, close
        APIs etc.
        """
        await self.aclose()

    async def start(self) -> None:
        await self.event_bus.start()

        api_factory = ApiFactory(self._api_config)
        self._ya_market_api = api_factory.create_market_api_client()
        self._ya_activity_api = api_factory.create_activity_api_client()
        self._ya_payment_api = api_factory.create_payment_api_client()
        self._ya_net_api = api_factory.create_net_api_client()

        if self._collect_payment_events:
            self._invoice_event_collector.start_collecting_events()
            self._debit_note_event_collector.start_collecting_events()

        await self.event_bus.emit(SessionStarted(self))

    async def aclose(self) -> None:
        await self.event_bus.emit(ShutdownStarted(self))
        self._set_no_more_children()
        self._stop_event_collectors()
        await self._close_autoclose_resources()
        await self._close_apis()
        await self.event_bus.emit(ShutdownFinished(self))

        await self.event_bus.stop()

    def _stop_event_collectors(self) -> None:
        demands = self.all_resources(Demand)
        batches = self.all_resources(PoolingBatch)
        payment_event_collectors = [self._invoice_event_collector, self._debit_note_event_collector]

        for event_collector in demands + batches + payment_event_collectors:
            event_collector.stop_collecting_events()

    def _set_no_more_children(self) -> None:
        for resources in self._resources.values():
            for resource in resources.values():
                resource.set_no_more_children()

    async def _close_apis(self) -> None:
        await asyncio.gather(
            self._ya_market_api.close(),
            self._ya_activity_api.close(),
            self._ya_payment_api.close(),
            self._ya_net_api.close(),
        )

    async def _close_autoclose_resources(self) -> None:
        agreement_msg = "Work finished"
        activity_tasks = [r.destroy() for r in self._autoclose_resources if isinstance(r, Activity)]
        agreement_tasks = [
            r.terminate(agreement_msg)
            for r in self._autoclose_resources
            if isinstance(r, Agreement)
        ]
        demand_tasks = [r.unsubscribe() for r in self._autoclose_resources if isinstance(r, Demand)]
        allocation_tasks = [
            r.release() for r in self._autoclose_resources if isinstance(r, Allocation)
        ]
        network_tasks = [r.remove() for r in self._autoclose_resources if isinstance(r, Network)]
        if activity_tasks:
            await asyncio.gather(*activity_tasks)
        if agreement_tasks:
            await asyncio.gather(*agreement_tasks)
        if demand_tasks:
            await asyncio.gather(*demand_tasks)
        if allocation_tasks:
            await asyncio.gather(*allocation_tasks)
        if network_tasks:
            await asyncio.gather(*network_tasks)

    ###########################
    #   Create new resources
    async def create_allocation(
        self,
        amount: Union[Decimal, float],
        network: str = payload_defaults.DEFAULT_PAYMENT_NETWORK,
        driver: str = payload_defaults.DEFAULT_PAYMENT_DRIVER,
        autoclose: bool = True,
    ) -> Allocation:
        """Create a new allocation.

        :param amount: Amount of GLMs to be allocated
        :param network: Payment network
        :param driver: Payment driver
        :param autoclose: Release allocation on :func:`__aexit__`
        """
        decimal_amount = Decimal(amount)

        #   TODO (?): https://github.com/golemfactory/golem-core-python/issues/34
        allocation = await Allocation.create_any_account(self, decimal_amount, network, driver)
        if autoclose:
            self.add_autoclose_resource(allocation)
        return allocation

    async def create_demand(
        self,
        payload: Payload,
        subnet: Optional[str] = payload_defaults.DEFAULT_SUBNET,
        expiration: Optional[datetime] = None,
        allocations: Iterable[Allocation] = (),
        autoclose: bool = True,
        autostart: bool = True,
    ) -> Demand:
        """Subscribe a new demand.

        :param payload: Details of the demand
        :param subnet: Subnet tag
        :param expiration: Timestamp when all agreements based on this demand will expire
            TODO: is this correct?
        :param allocations: Allocations that will be included in the description of this demand.
        :param autoclose: Unsubscribe demand on :func:`__aexit__`
        :param autostart: Immediately start collecting yagna events for this :any:`Demand`.
            Without autostart events for this demand will start being collected after a call to
            :func:`Demand.start_collecting_events`.
        """
        if expiration is None:
            expiration = datetime.now(timezone.utc) + payload_defaults.DEFAULT_LIFETIME

        builder = DemandBuilder()
        await builder.add(payload_defaults.ActivityInfo(expiration=expiration, multi_activity=True))
        await builder.add(payload_defaults.NodeInfo(subnet_tag=subnet))

        await builder.add(payload)
        await self._add_builder_allocations(builder, allocations)

        demand = await Demand.create_from_properties_constraints(
            self, builder.properties, builder.constraints
        )

        if autostart:
            demand.start_collecting_events()
        if autoclose:
            self.add_autoclose_resource(demand)
        return demand

    async def create_network(
        self,
        ip: str,
        mask: Optional[str] = None,
        gateway: Optional[str] = None,
        autoclose: bool = True,
        add_requestor: bool = True,
        requestor_ip: Optional[str] = None,
    ) -> Network:
        """Create a new :any:`Network`.

        :param ip: IP address of the network. May contain netmask, e.g. `192.168.0.0/24`.
        :param mask: Optional netmask (only if not provided within the `ip` argument).
        :param gateway: Optional gateway address for the network.
        :param autoclose: Remove network on :func:`__aexit__`
        :param add_requestor: If True, adds requestor with ip `requestor_ip` to the network.
            If False, requestor will be able to interact with other nodes only
            after an additional call to :func:`add_to_network`.
        :param requestor_ip: Ip of the requestor node in the network. Ignored if not
            `add_requestor`. If `None`, next free ip will be assigned.
        """
        network = await Network.create(self, ip, mask, gateway)
        if autoclose:
            self.add_autoclose_resource(network)
        if add_requestor:
            await self.add_to_network(network, requestor_ip)
        return network

    async def _add_builder_allocations(
        self, builder: DemandBuilder, allocations: Iterable[Allocation]
    ) -> None:
        # TODO (?): https://github.com/golemfactory/golem-core-python/issues/35

        for allocation in allocations:
            await builder.add(await allocation.get_demand_spec())

    ###########################
    #   Single-resource factories for already existing resources
    def allocation(self, allocation_id: str) -> Allocation:
        """Return an :any:`Allocation` with a given id (assumed to be correct, there is no \
        validation)."""
        return Allocation(self, allocation_id)

    def debit_note(self, debit_note_id: str) -> DebitNote:
        """Return an :any:`DebitNote` with a given id (assumed to be correct, there is no \
        validation)."""
        return DebitNote(self, debit_note_id)

    def invoice(self, invoice_id: str) -> Invoice:
        """Return an :any:`Invoice` with a given id (assumed to be correct, there is no \
        validation)."""
        return Invoice(self, invoice_id)

    def demand(self, demand_id: str) -> Demand:
        """Return a :any:`Demand` with a given id (assumed to be correct, there is no \
        validation)."""
        return Demand(self, demand_id)

    def proposal(self, proposal_id: str, demand_id: str) -> Proposal:
        """Return a :any:`Proposal` with a given id (assumed to be correct, there is no validation).

        Id of a proposal has a meaning only in the context of a demand,
        so demand_id is also necessary (and also not validated).
        """
        demand = self.demand(demand_id)
        return demand.proposal(proposal_id)

    def agreement(self, agreement_id: str) -> Agreement:
        """Return an :any:`Agreement` with a given id (assumed to be correct, there is no \
        validation)."""
        return Agreement(self, agreement_id)

    def activity(self, activity_id: str) -> Activity:
        """Return an :any:`Activity` with a given id (assumed to be correct, there is no \
        validation)."""
        return Activity(self, activity_id)

    def batch(self, batch_id: str, activity_id: str) -> PoolingBatch:
        """Return a :any:`PoolingBatch` with a given id (assumed to be correct, there is no \
        validation).

        Id of a batch has a meaning only in the context of an activity,
        so activity_id is also necessary (and also not validated).
        """
        activity = self.activity(activity_id)
        return activity.batch(batch_id)

    ##########################
    #   Multi-resource factories for already existing resources
    async def allocations(self) -> List[Allocation]:
        """Return a list of :any:`Allocation` objects corresponding to all current allocations.

        These are all allocations related to the current APP_KEY - it doesn't matter if they were
        created with this :class:`GolemNode` instance (or if :class:`GolemNode` was used at all).
        """
        return await Allocation.get_all(self)

    async def demands(self) -> List[Demand]:
        """Return a list of :any:`Demand` objects corresponding to all current demands.

        These are all demands subscribed with the current APP_KEY - it doesn't matter if they were
        created with this :class:`GolemNode` instance (or if :class:`GolemNode` was used at all).
        """
        return await Demand.get_all(self)

    async def invoices(self) -> List[Invoice]:
        """Return a list of :any:`Invoice` objects corresponding to all invoices received by this \
        node."""
        return await Invoice.get_all(self)

    async def debit_notes(self) -> List[DebitNote]:
        """Return a list of :any:`DebitNote` objects corresponding to all debit notes received by \
        this node."""
        return await DebitNote.get_all(self)

    async def networks(self) -> List[Network]:
        """Return a list of :any:`Network` objects corresponding to all networks created by this \
        node.

        These are all networks created with the current APP_KEY - it doesn't matter if they were
        created with this :class:`GolemNode` instance (or if :class:`GolemNode` was used at all).
        """
        return await Network.get_all(self)

    ##########################
    #   Events
    @property
    def event_bus(self) -> EventBus:
        """Return the :any:`EventBus` used by this :class:`GolemNode`.

        Any :any:`Event` triggered by this :class:`GolemNode` or any related object
        will be sent there and passed to registered listeners.
        """
        return self._event_bus

    #########
    #   Other
    async def add_to_network(self, network: Network, ip: Optional[str] = None) -> None:
        """Add requestor to the network.

        :param network: A :any:`Network` we're adding the requestor to.
        :param ip: IP of the requestor node, defaults to a new free IP in the network.

        This is only necessary if we either called :func:`create_network` with
        `add_requestor=False`, or we want the requestor to have multiple IPs in the network
        (TODO: is there a scenario where this makes sense?).
        """
        await network.add_requestor_ip(ip)

    def add_autoclose_resource(
        self, resource: Union["Allocation", "Demand", "Agreement", "Activity", "Network"]
    ) -> None:
        self._autoclose_resources.add(resource)

    def all_resources(self, cls: Type[TResource]) -> List[TResource]:
        """Return all known resources of a given type."""
        return list(self._resources[cls].values())  # type: ignore

    def __str__(self) -> str:
        lines = [
            f"{type(self).__name__}(",
            f"  app_key = {self.app_key},",
            f"  app_session_id = {self.app_session_id},",
            f"  market_url = {self._api_config.market_url},",
            f"  payment_url = {self._api_config.payment_url},",
            f"  activity_url = {self._api_config.activity_url},",
            f"  net_url = {self._api_config.net_url},",
            ")",
        ]
        return "\n".join(lines)
