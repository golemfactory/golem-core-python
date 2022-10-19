
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

.. autofunction:: golem_api.high.execute_tasks.execute_tasks

Mid-level API
=============

Mid-level API consists of reusable components that can serve as a building blocks for various
different applications.
 
General components
------------------------

Classes in this section know nothing about any Golem-specific logic. They should one day be extracted to a sparate library.

.. autoclass:: golem_api.mid.Chain
.. autoclass:: golem_api.mid.Map
    :members: __init__, __call__
.. autoclass:: golem_api.mid.Zip
.. autoclass:: golem_api.mid.Buffer
    :members: __init__


Golem-specific components
------------------------------
Components in this section contain the common logic that is shared by various Golem applications.

.. autoclass:: golem_api.mid.SimpleScorer
    :members: __init__, __call__
.. autoclass:: golem_api.mid.ActivityPool
    :members: __init__, __call__
.. autofunction:: golem_api.mid.default_negotiate
.. autofunction:: golem_api.mid.default_create_agreement
.. autofunction:: golem_api.mid.default_create_activity
.. autofunction:: golem_api.mid.default_prepare_activity


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

.. autoclass:: golem_api.low.payment.DebitNote

.. autoclass:: golem_api.low.payment.Invoice

Activity API
------------

.. autoclass:: golem_api.low.activity.Activity

.. autoclass:: golem_api.low.activity.PoolingBatch

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
