import os
from dataclasses import dataclass, field
from functools import partial
from typing import Optional

import ya_activity
import ya_market
import ya_net
import ya_payment
from typing_extensions import Final

DEFAULT_YAGNA_API_URL: Final[str] = "http://127.0.0.1:7465"


class MissingConfiguration(Exception):
    def __init__(self, key: str, description: str):
        self._key = key
        self._description = description

    def __str__(self) -> str:
        return f"Missing configuration for {self._description}. Please set env var {self._key}."


@dataclass
class ApiConfig:
    """Yagna low level API configuration.

    Attributes:
        app_key: Yagna application key.
            If not provided, the default is to get the value from `YAGNA_APPKEY` environment
            variable.
            If no value will be found MissingConfiguration error will be thrown
        api_url: base URL or all REST API URLs. Example value: http://127.0.10.10:7500
            (no trailing slash).
            Uses YAGNA_API_URL environment variable
        market_url: If not provided `api_url` will be used to construct it.
            Uses YAGNA_MARKET_URL environment variable
        payment_url: If not provided `api_url` will be used to construct it.
            Uses YAGNA_PAYMENT_URL environment variable
        net_url: Uses If not provided `api_url` will be used to construct it.
            YAGNA_NET_URL environment variable
        activity_url: If not provided `api_url` will be used to construct it.
            Uses YAGNA_ACTIVITY_URL environment variable
    """

    app_key: str = field(default_factory=partial(os.getenv, "YAGNA_APPKEY"))  # type: ignore[assignment]
    api_url: str = field(default_factory=partial(os.getenv, "YAGNA_API_URL", DEFAULT_YAGNA_API_URL))  # type: ignore[assignment]
    market_url: str = field(default_factory=partial(os.getenv, "YAGNA_MARKET_URL"))  # type: ignore[assignment]
    payment_url: str = field(default_factory=partial(os.getenv, "YAGNA_PAYMENT_URL"))  # type: ignore[assignment]
    net_url: str = field(default_factory=partial(os.getenv, "YAGNA_NET_URL"))  # type: ignore[assignment]
    activity_url: str = field(default_factory=partial(os.getenv, "YAGNA_ACTIVITY_URL"))  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.app_key is None:
            raise MissingConfiguration(
                key="YAGNA_APPKEY", description="API authentication token"
            )
        self.market_url: str = self.__resolve_url(self.market_url, "/market-api/v1")
        self.payment_url: str = self.__resolve_url(self.payment_url, "/payment-api/v1")
        self.activity_url: str = self.__resolve_url(
            self.activity_url, "/activity-api/v1"
        )
        self.net_url: str = self.__resolve_url(self.net_url, "/net-api/v1")

    def __resolve_url(self, given_url: Optional[str], prefix: str) -> str:
        return given_url or f"{self.api_url}{prefix}"


class ApiFactory(object):
    """
    REST API's setup and top-level access utility.

    By default, it expects the yagna daemon to be available locally and listening on the
    default port. The urls for the specific APIs are then based on this default base URL.
    """

    def __init__(
        self,
        api_config: ApiConfig,
    ):
        self.__api_config: ApiConfig = api_config

    def create_market_api_client(self) -> ya_market.ApiClient:
        """Return a REST client for the Market API."""
        cfg = ya_market.Configuration(host=self.__api_config.market_url)
        return ya_market.ApiClient(
            configuration=cfg,
            header_name="authorization",
            header_value=f"Bearer {self.__api_config.app_key}",
        )

    def create_payment_api_client(self) -> ya_payment.ApiClient:
        """Return a REST client for the Payment API."""
        cfg = ya_payment.Configuration(host=self.__api_config.payment_url)
        return ya_payment.ApiClient(
            configuration=cfg,
            header_name="authorization",
            header_value=f"Bearer {self.__api_config.app_key}",
        )

    def create_activity_api_client(self) -> ya_activity.ApiClient:
        """Return a REST client for the Activity API."""
        cfg = ya_activity.Configuration(host=self.__api_config.activity_url)
        return ya_activity.ApiClient(
            configuration=cfg,
            header_name="authorization",
            header_value=f"Bearer {self.__api_config.app_key}",
        )

    def create_net_api_client(self) -> ya_net.ApiClient:
        """Return a REST client for the Net API."""
        cfg = ya_net.Configuration(host=self.__api_config.net_url)
        return ya_net.ApiClient(
            configuration=cfg,
            header_name="authorization",
            header_value=f"Bearer {self.__api_config.app_key}",
        )
