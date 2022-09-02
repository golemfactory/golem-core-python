
**************************
Golem Python API Reference
**************************


GolemNode
=========

.. autoclass:: golem_api.GolemNode
    :members: __init__, __aenter__, __aexit__, 
              create_allocation, create_demand, 
              allocation, demand, proposal, agreement, 
              allocations, demands,
              event_bus

High-Level API
==============

[Nothing here yet. Task API, Service API etc.]

Mid-level API
=============

Mid-level API consists of reusable components that can serve as a building blocks for various
different applications.

Important temporary note: this will be easier to understand after reading the `run.py` example.

Chain
-----

.. autoclass:: golem_api.mid.Chain

Chain components
----------------

Components in this section can be used as parts of the Chain (but don't have to).

.. autoclass:: golem_api.mid.SimpleScorer
    :members: __init__, __call__

.. autoclass:: golem_api.mid.DefaultNegotiator
    :members: __init__, __call__

.. autoclass:: golem_api.mid.AgreementCreator
    :members: __call__


Low-level API
=============

Low-level objects correspond to resources in the Golem Network.
They make no assumptions about any higher-level components that interact with them.
Capabilities of the low-level API should match `yagna` capabilities, i.e. anything one can
do by direct `yagna` interactions should also be possible - and, hopefully, more convenient - 
by performing operations on the low-level objects.

Resource
--------

.. autoclass:: golem_api.low.resource.Resource
    :members: id, node,
              get_data, data,
              parent, children, child_aiter, 
              events,

Market API
----------

.. autoclass:: golem_api.low.market.Demand
    :members: initial_proposals, start_collecting_events, stop_collecting_events, unsubscribe, proposal

.. autoclass:: golem_api.low.market.Proposal
    :members: initial, draft, rejected, demand,
              respond, responses, reject, create_agreement

.. autoclass:: golem_api.low.market.Agreement
    :members: confirm, wait_for_approval, terminate

Payment API
-----------

.. autoclass:: golem_api.low.payment.Allocation
    :members: release

Events
======

.. autoclass:: golem_api.event_bus.EventBus
    :members: listen, resource_listen, emit

.. automodule:: golem_api.events
    :members:

Logging
=======

.. autoclass:: golem_api.default_logger.DefaultLogger
    :members: __init__, file_name, logger, on_event
