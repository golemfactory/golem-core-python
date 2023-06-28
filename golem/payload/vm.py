import logging
from abc import ABC
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from typing import Final, List, Literal, Optional, Tuple

from dns.exception import DNSException
from srvresolver.srv_record import SRVRecord
from srvresolver.srv_resolver import SRVResolver

from golem.payload import defaults
from golem.payload.base import Payload, constraint, prop
from golem.payload.constraints import Constraints
from golem.payload.properties import Properties
from golem.utils.http import make_http_get_request, make_http_head_request

DEFAULT_REPO_URL_SRV: Final[str] = "_girepo._tcp.dev.golem.network"
DEFAULT_REPO_URL_FALLBACK: Final[str] = "http://girepo.dev.golem.network:8000"
DEFAULT_REPO_URL_TIMEOUT: Final[timedelta] = timedelta(seconds=10)

VmCaps = Literal["vpn", "inet", "manifest-support"]

logger = logging.getLogger(__name__)


class VmPayloadException(Exception):
    """Exception raised on any problems related to the payload for "vm" runtime."""


class VmPackageFormat(Enum):
    """Enumeration of available image formats for "vm" runtime."""

    UNKNOWN = None
    GVMKIT_SQUASH = "gvmkit-squash"


@dataclass
class BaseVmPayload(Payload, ABC):
    """Declarative description of common payload parameters for "vm" runtime."""

    runtime: str = constraint(defaults.RUNTIME_NAME, "=", default="vm")
    capabilities: List[VmCaps] = constraint(
        defaults.RUNTIME_CAPABILITIES, "=", default_factory=list
    )

    min_mem_gib: float = constraint(defaults.INF_MEM, ">=", default=0.5)
    min_storage_gib: float = constraint(defaults.INF_STORAGE, ">=", default=2.0)
    min_cpu_threads: int = constraint(defaults.INF_CPU_THREADS, ">=", default=1)

    package_format: VmPackageFormat = prop(
        "golem.srv.comp.vm.package_format", default=VmPackageFormat.GVMKIT_SQUASH
    )


@dataclass
class _VmPayload(Payload, ABC):
    package_url: str = prop("golem.srv.comp.task_package")


# TODO: Use kw_only=True on python 3.10+
@dataclass
class VmPayload(BaseVmPayload, _VmPayload):
    """Declarative description of payload for "vm" runtime."""


@dataclass
class _ManifestVmPayload(Payload, ABC):
    manifest: str = prop("golem.srv.comp.payload")
    manifest_sig: Optional[str] = prop("golem.srv.comp.payload.sig", default=None)
    manifest_sig_algorithm: Optional[str] = prop(
        "golem.srv.comp.payload.sig.algorithm", default=None
    )
    manifest_cert: Optional[str] = prop("golem.srv.comp.payload.cert", default=None)


# TODO: Use kw_only=True on python 3.10+
@dataclass
class ManifestVmPayload(BaseVmPayload, _ManifestVmPayload):
    """Declarative description of payload for "vm" runtime, with Computation Manifest flavor."""


@dataclass
class _RepositoryVmPayload(ABC):
    image_hash: str
    image_url: Optional[str] = None
    package_url: Optional[str] = prop("golem.srv.comp.task_package", default=None)


# TODO: Use kw_only=True on python 3.10+
@dataclass
class RepositoryVmPayload(BaseVmPayload, _RepositoryVmPayload):
    """Declarative description of payload for "vm" runtime, with ability to resolve "image_url" \
    parameter from remote repository."""

    async def _resolve_package_url(self) -> None:
        if self.image_url:
            await check_image_url(self.image_url)
            image_url = self.image_url
        else:
            repo_url = await resolve_repository_url()
            image_url = await resolve_image_url(repo_url, self.image_hash)

        self.package_url = get_package_url(self.image_hash, image_url)

    async def build_properties_and_constraints(self) -> Tuple[Properties, Constraints]:
        if self.package_url is None:
            await self._resolve_package_url()

        return await super().build_properties_and_constraints()


async def resolve_repository_url(
    repo_srv: str = DEFAULT_REPO_URL_SRV,
    fallback_url: str = DEFAULT_REPO_URL_FALLBACK,
    timeout: timedelta = DEFAULT_REPO_URL_TIMEOUT,
) -> str:
    """Resolve url of the image repository with help of DNS records.

    :param repo_srv: the SRV record that keep repository url
    :param fallback_url: fallback url in case there's a problem resolving SRV record
    :param timeout: maximum time window for SRV resolving
    :return: the full repository url
    """
    try:
        try:
            # TODO: Async implementation is needed
            srv: Optional[SRVRecord] = SRVResolver.resolve_random(
                repo_srv,
                timeout=int(timeout.total_seconds()),
            )
        except DNSException as e:
            raise VmPayloadException("Could not resolve Golem package repository address!") from e

        if not srv:
            raise VmPayloadException("Golem package repository is currently unavailable!")
    except Exception as e:
        # this is a temporary fallback for a problem resolving the SRV record
        logger.warning(
            "Problem resolving %s, falling back to %s, exception: %s", repo_srv, fallback_url, e
        )
        return fallback_url

    return f"http://{srv.host}:{srv.port}"


async def check_image_url(image_url: str) -> None:
    """Check if given image url exists."""

    await make_http_head_request(image_url, raise_exceptions=True)


async def resolve_image_url(repo_url: str, image_hash: str) -> str:
    """Fetch image url from given repository url and image hash."""

    return await make_http_get_request(f"{repo_url}/image.{image_hash}.link", raise_exceptions=True)


def get_package_url(image_hash: str, image_url: str) -> str:
    """Turn image hash and image url into package url format."""
    return f"hash:sha3:{image_hash}:{image_url}"
