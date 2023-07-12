import inspect
import logging
from datetime import datetime, timezone
from functools import wraps
from typing import TYPE_CHECKING, Optional


if TYPE_CHECKING:
    from golem.event_bus import Event


DEFAULT_LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "[%(asctime)s %(levelname)s %(name)s] %(message)s",
        },
    },
    "handlers": {
        "console": {
            "formatter": "default",
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "": {
            "level": "INFO",
            "handlers": [
                "console",
            ],
        },
        "asyncio": {
            "level": "DEBUG",
        },
        "golem": {
            "level": "INFO",
        },
        "golem.managers": {
            "level": "INFO",
        },
        "golem.managers.negotiation": {
            "level": "INFO",
        },
        "golem.managers.proposal": {
            "level": "INFO",
        },
        "golem.managers.work": {
            "level": "INFO",
        },
        "golem.managers.agreement": {
            "level": "INFO",
        },
    },
}

logger = logging.getLogger()
class _YagnaDatetimeFormatter(logging.Formatter):
    """Custom log Formatter that formats datetime using the same convention yagna uses."""

    LOCAL_TZ = datetime.now(timezone.utc).astimezone().tzinfo

    def formatTime(self, record: logging.LogRecord, datefmt: Optional[str] = None) -> str:
        """Format datetime; example: `2021-06-11T14:55:43.156.123+0200`."""
        dt = datetime.fromtimestamp(record.created, tz=self.LOCAL_TZ)
        millis = f"{(dt.microsecond // 1000):03d}"
        return dt.strftime(f"%Y-%m-%dT%H:%M:%S.{millis}%z")


class DefaultLogger:
    """Dump all events to a file.

    Usage::

        golem = GolemNode()
        await golem.event_bus.on(Event, DefaultLogger().on_event)

    Or::

        DefaultLogger().logger.debug("What's up?")
    """

    def __init__(self, file_name: str = "log.log"):
        """Init DefaultLogger.

        :param file_name: Name of the file where all events will be dumped.
        """
        self._file_name = file_name
        self._logger = self._prepare_logger()

    @property
    def file_name(self) -> str:
        """Name of the file where all events will be dumped."""
        return self._file_name

    @property
    def logger(self) -> logging.Logger:
        """Logger that just dumps everything to file :any:`file_name`."""
        return self._logger

    def _prepare_logger(self) -> logging.Logger:
        logger = logging.getLogger("golem")
        logger.setLevel(logging.DEBUG)

        format_ = "[%(asctime)s %(levelname)s %(name)s] %(message)s"
        formatter = _YagnaDatetimeFormatter(fmt=format_)

        file_handler = logging.FileHandler(filename=self._file_name, mode="w", encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)

        return logger

    async def on_event(self, event: "Event") -> None:
        """Handle event produced by :any:`EventBus.on`."""
        self.logger.info(event)


def trace_span(name: Optional[str] = None, show_arguments: bool = False, show_results: bool = True):
    def wrapper(f):
        span_name = name if name is not None else f.__name__

        @wraps(f)
        def sync_wrapped(*args, **kwargs):
            if show_arguments:
                args_str = ', '.join(repr(a) for a in args)
                kwargs_str = ', '.join('{}={}'.format(k, repr(v)) for (k, v) in kwargs.items())
                final_name = f'{span_name}({args_str}, {kwargs_str})'
            else:
                final_name = span_name

            logger.debug(f"{final_name}...")

            try:
                result = f(*args, **kwargs)
            except Exception as e:
                logger.debug(f"{final_name} failed with `{e}`")
                raise

            if show_results:
                logger.debug(f"{final_name} done with `{result}`")
            else:
                logger.debug(f"{final_name} done")

            return result

        @wraps(f)
        async def async_wrapped(*args, **kwargs):
            if show_arguments:
                args_str = ', '.join(repr(a) for a in args)
                kwargs_str = ', '.join('{}={}'.format(k, repr(v)) for (k, v) in kwargs.items())
                final_name = f'{span_name}({args_str}, {kwargs_str})'
            else:
                final_name = span_name

            logger.debug(f"{final_name}...")

            try:
                result = await f(*args, **kwargs)
            except Exception as e:
                logger.debug(f"{final_name} failed with `{e}`")
                raise

            if show_results:
                logger.debug(f"{final_name} done with `{result}`")
            else:
                logger.debug(f"{final_name} done")

            return result

        return async_wrapped if inspect.iscoroutinefunction(f) else sync_wrapped

    return wrapper
