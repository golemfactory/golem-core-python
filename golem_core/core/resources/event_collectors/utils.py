import asyncio
import json
from typing import Union

import aiohttp
import ya_activity
import ya_market
import ya_payment


def is_intermittent_error(e: Exception) -> bool:
    """Check if `e` indicates an intermittent communication failure such as network_api timeout."""

    is_timeout_exception = isinstance(e, asyncio.TimeoutError) or (
        isinstance(
            e,
            (ya_activity.ApiException, ya_market.ApiException, ya_payment.ApiException),
        )
        and e.status in (408, 504)
    )

    return (
        is_timeout_exception
        or isinstance(e, aiohttp.ServerDisconnectedError)
        # OS error with errno 32 is "Broken pipe"
        or (isinstance(e, aiohttp.ClientOSError) and e.errno == 32)
    )


def is_gsb_endpoint_not_found_error(
    err: Union[
        ya_activity.ApiException, ya_market.ApiException, ya_payment.ApiException
    ]
) -> bool:
    """Check if `err` is caused by "Endpoint address not found" GSB error."""

    if err.status != 500:
        return False
    try:
        msg = json.loads(err.body)["message"]
        return "GSB error" in msg and "endpoint address not found" in msg
    except Exception:
        return False
