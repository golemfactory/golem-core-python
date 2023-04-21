
*******************************
Golem Python Core API Reference
*******************************


GolemNode
=========

.. autoclass:: golem_core.core.golem_node.GolemNode
    :members: __init__, __aenter__, __aexit__, 
              create_allocation, create_demand, create_network,
              allocation, debit_note, invoice, 
              demand, proposal, agreement,
              activity, batch,
              allocations, demands, networks,
              event_bus, add_to_network

.. High-Level API
.. ==============

.. .. autofunction:: golem_core.high.execute_tasks.execute_tasks

Mid-level API
=============

Mid-level API consists of reusable components that can serve as a building blocks for various
different applications.
 
General components
------------------------

Classes in this section know nothing about any Golem-specific logic. They should one day be extracted to a sparate library.


.. autoclass:: golem_core.pipeline.Sort
    :members: __init__, __call__
.. autoclass:: golem_core.pipeline.Chain
.. autoclass:: golem_core.pipeline.Map
    :members: __init__, __call__
.. autoclass:: golem_core.pipeline.Zip
.. autoclass:: golem_core.pipeline.Buffer
    :members: __init__, __call__
.. autoclass:: golem_core.pipeline.Limit
    :members: __init__


Golem-specific components
------------------------------
Components in this section contain the common logic that is shared by various Golem applications.

.. autofunction:: golem_core.core.market_api.default_negotiate
.. autofunction:: golem_core.core.market_api.default_create_agreement
.. autofunction:: golem_core.core.market_api.default_create_activity
.. autofunction:: golem_core.core.activity_api.default_prepare_activity


Low-level API
=============

Low-level objects correspond to resources in the Golem Network.
They make no assumptions about any higher-level components that interact with them.
Capabilities of the low-level API should match `yagna` capabilities, i.e. anything one can
do by direct `yagna` interactions should also be possible - and, hopefully, more convenient - 
by performing operations on the low-level objects.

Resource
--------

.. autoclass:: golem_core.core.resources.Resource
    :members: id, node,
              get_data, data,
              parent, children, child_aiter, 
              events,

Market API
----------

.. autoclass:: golem_core.core.market_api.Demand
    :members: initial_proposals, unsubscribe, proposal

.. autoclass:: golem_core.core.market_api.Proposal
    :members: initial, draft, rejected, demand,
              respond, responses, reject, create_agreement

.. autoclass:: golem_core.core.market_api.Agreement
    :members: confirm, wait_for_approval, terminate, create_activity,
              invoice, activities, close_all

Payment API
-----------

.. autoclass:: golem_core.core.payment_api.Allocation
    :members: release

.. autoclass:: golem_core.core.payment_api.DebitNote
    :members: accept_full

.. autoclass:: golem_core.core.payment_api.Invoice
    :members: accept_full

Activity API
------------

.. autoclass:: golem_core.core.activity_api.Activity
    :members: execute_commands, execute_script, destroy,
              idle, destroyed, wait_busy, wait_idle, wait_destroyed,
              debit_notes, batch

.. autoclass:: golem_core.core.activity_api.PoolingBatch
    :members: wait, events, done, success

.. autoclass:: golem_core.core.activity_api.Script
    :members: add_command

Network API
-----------

.. autoclass:: golem_core.core.network_api.Network
    :members: create_node, deploy_args, refresh_nodes, remove

Commands
--------

.. autoclass:: golem_core.core.activity_api.commands.Command
.. autoclass:: golem_core.core.activity_api.commands.Deploy
.. autoclass:: golem_core.core.activity_api.commands.Start
.. autoclass:: golem_core.core.activity_api.commands.Run
    :members: __init__
.. autoclass:: golem_core.core.activity_api.commands.SendFile
    :members: __init__
.. autoclass:: golem_core.core.activity_api.commands.DownloadFile
    :members: __init__

Exceptions
----------

.. autoclass:: golem_core.core.resources.ResourceNotFound
    :members: resource
.. autoclass:: golem_core.core.payment_api.NoMatchingAccount
    :members: network, driver
.. autoclass:: golem_core.core.activity_api.BatchTimeoutError
    :members: batch, timeout
.. autoclass:: golem_core.core.activity_api.BatchError
    :members: batch
.. autoclass:: golem_core.core.activity_api.CommandFailed
    :members: batch
.. autoclass:: golem_core.core.activity_api.CommandCancelled
    :members: batch
.. autoclass:: golem_core.core.network_api.NetworkFull
    :members: network

Events
======

.. autoclass:: golem_core.core.events.EventBus
    :members: listen, resource_listen, emit

.. automodule:: golem_core.core.events.event
    :members:

.. automodule:: golem_core.core.activity_api.events
    :members:

.. automodule:: golem_core.core.resources.events
    :members:

Logging
=======

.. autoclass:: golem_core.utils.logging.DefaultLogger
    :members: __init__, file_name, logger, on_event

Managers
========

.. autoclass:: golem_core.managers.DefaultPaymentManager
    :members: __init__, terminate_agreements, wait_for_invoices
