# `yapapi` dependencies

- yapapi is locked at `^0.9.3` in the [toml](/pyproject.toml)

- [README](/README.md) mention `yapapi` in the line 7

  >blender - just like the `yapapi` blender

- [service.py](/service.py)
  - uses `yapapi.payload.vm` for `Payload`'s `capabilities` `vm.VM_CAPS_VPN`

- [commands.py](/golem_core/commands.py)
  - `from yapapi.storage import Destination, Source` for typing
  - `from yapapi.storage.gftp import GftpProvider` in `SendFile` and `DownloadFile` commands for file interactions

- [default_logger.py](/golem_core/default_logger.py)
  - `from yapapi.log import _YagnaDatetimeFormatter` as `formatter`
    > yapapi docs: `Custom log Formatter that formats datetime using the same convention yagna uses.`

- [golem_node.py](/golem_core/golem_node.py)
  - `from yapapi import rest` used to access yagna api bindings. `golem_core/low` is using `ya_` libs for typing and DTO(??)

    ```python
    # golem-core
    self._api_config = rest.Configuration(app_key, url=base_url)
    ...
    self._ya_market_api = self._api_config.market()
    self._ya_activity_api = self._api_config.activity()
    self._ya_payment_api = self._api_config.payment()
    self._ya_net_api = self._api_config.net()
    ...
    # yapapi
    import ya_market  # type: ignore
    import ya_payment  # type: ignore
    import ya_activity  # type: ignore
    import ya_net  # type: ignore
    ```

  - `from yapapi.engine import DEFAULT_DRIVER, DEFAULT_NETWORK, DEFAULT_SUBNET` for default params values
  - `from yapapi.props.builder import DemandBuilder` used in `create_demand` method
  - `from yapapi import props` *as above*

- [payload.py](/golem_core/payload.py)
  - `from yapapi.payload import Payload as YapapiPayload, vm` - uses `YapapiPayload` as base class for `Payload` which adds `def from_image_hash`:
    > A non-async wrapper for `yapapi.vm.repo()` function.

- [cli/\_\_init__.py](/golem_core/cli/__init__.py)
  - `from yapapi.engine import DEFAULT_NETWORK, DEFAULT_DRIVER, DEFAULT_SUBNET` for default params values

- [cli/utils.py](/golem_core/cli/utils.py)
  - `from yapapi.props.base import constraint` in `CliPayload` (inherits from [`Payload`](/golem_core/payload.py)) to alter `runtime`
  - `from yapapi.props import inf` *as above*

- [exceptions.py](/golem_core/exceptions.py)
  - `from yapapi.engine import NoPaymentAccountError` in `NoMatchingAccount(Exception)` so it yields the same message when raise
  
    ```python
    msg = str(NoPaymentAccountError(driver, network))
    ```

- [low/yagna_event_collector.py](/golem_core/low/yagna_event_collector.py)
  - `from yapapi.rest.common import is_intermittent_error` and `from yapapi.rest.activity import _is_gsb_endpoint_not_found_error` in `_collect_yagna_events` to ignore some exceptions when getting events from yagna  

    ```python
    while True:
    args = self._collect_events_args()
    kwargs = self._collect_events_kwargs()
    try:
        events = await self._collect_events_func(*args, **kwargs)
    except Exception as e:
        if is_intermittent_error(e):
            continue
        elif _is_gsb_endpoint_not_found_error_wrapper(e):
            gsb_endpoint_not_found_cnt += 1
            if gsb_endpoint_not_found_cnt <= MAX_GSB_ENDPOINT_NOT_FOUND_ERRORS:
                await asyncio.sleep(3)
                continue

        raise
    ```
