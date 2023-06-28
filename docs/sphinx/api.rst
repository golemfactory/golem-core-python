
*******************************
Golem Python Core API Reference
*******************************


GolemNode
=========

.. autoclass:: golem.node.GolemNode
    :members: __init__, __aenter__, __aexit__, 
              create_allocation, create_demand, create_network,
              allocation, debit_note, invoice, 
              demand, proposal, agreement,
              activity, batch,
              allocations, demands, networks,
              event_bus, add_to_network

.. High-Level API
.. ==============

.. .. autofunction:: golem.high.execute_tasks.execute_tasks

Mid-level API
=============

Mid-level API consists of reusable components that can serve as a building blocks for various
different applications.
 
General components
------------------------

Classes in this section know nothing about any Golem-specific logic. They should one day be extracted to a sparate library.


.. autoclass:: golem.pipeline.Sort
    :members: __init__, __call__
.. autoclass:: golem.pipeline.Chain
.. autoclass:: golem.pipeline.Map
    :members: __init__, __call__
.. autoclass:: golem.pipeline.Zip
.. autoclass:: golem.pipeline.Buffer
    :members: __init__, __call__
.. autoclass:: golem.pipeline.Limit
    :members: __init__


Golem-specific components
------------------------------
Components in this section contain the common logic that is shared by various Golem applications.

.. autofunction:: golem.resources.default_negotiate
.. autofunction:: golem.resources.default_create_agreement
.. autofunction:: golem.resources.default_create_activity
.. autofunction:: golem.resources.default_prepare_activity


Low-level API
=============

Low-level objects correspond to resources in the Golem Network.
They make no assumptions about any higher-level components that interact with them.
Capabilities of the low-level API should match `yagna` capabilities, i.e. anything one can
do by direct `yagna` interactions should also be possible - and, hopefully, more convenient - 
by performing operations on the low-level objects.

Resource
--------

.. autoclass:: golem.resources.Resource
    :members: id, node,
              get_data, data,
              parent, children, child_aiter, 
              events,

Market API
----------

.. autoclass:: golem.resources.Demand
    :members: initial_proposals, unsubscribe, proposal

.. autoclass:: golem.resources.Proposal
    :members: initial, draft, rejected, demand,
              respond, responses, reject, create_agreement

.. autoclass:: golem.resources.Agreement
    :members: confirm, wait_for_approval, terminate, create_activity,
              invoice, activities, close_all

Payment API
-----------

.. autoclass:: golem.resources.Allocation
    :members: release

.. autoclass:: golem.resources.DebitNote
    :members: accept_full

.. autoclass:: golem.resources.Invoice
    :members: accept_full

Activity API
------------

.. autoclass:: golem.resources.Activity
    :members: execute_commands, execute_script, destroy,
              idle, destroyed, wait_busy, wait_idle, wait_destroyed,
              debit_notes, batch

.. autoclass:: golem.resources.PoolingBatch
    :members: wait, events, done, success

.. autoclass:: golem.resources.Script
    :members: add_command

Network API
-----------

.. autoclass:: golem.resources.Network
    :members: create_node, deploy_args, refresh_nodes, remove

Commands
--------

.. autoclass:: golem.resources.Command
.. autoclass:: golem.resources.Deploy
.. autoclass:: golem.resources.Start
.. autoclass:: golem.resources.Run
    :members: __init__
.. autoclass:: golem.resources.SendFile
    :members: __init__
.. autoclass:: golem.resources.DownloadFile
    :members: __init__

Exceptions
----------

.. autoclass:: golem.resources.ResourceNotFound
    :members: resource
.. autoclass:: golem.resources.NoMatchingAccount
    :members: network, driver
.. autoclass:: golem.resources.BatchTimeoutError
    :members: batch, timeout
.. autoclass:: golem.resources.BatchError
    :members: batch
.. autoclass:: golem.resources.CommandFailed
    :members: batch
.. autoclass:: golem.resources.CommandCancelled
    :members: batch
.. autoclass:: golem.resources.NetworkFull
    :members: network

Events
======

.. automodule:: golem.event_bus.base
    :members:

.. automodule:: golem.resources.events
    :members:

Logging
=======

.. autoclass:: golem.utils.logging.DefaultLogger
    :members: __init__, file_name, logger, on_event

Managers
========

.. autoclass:: golem.managers.DefaultPaymentManager
    :members: __init__, terminate_agreements, wait_for_invoices
