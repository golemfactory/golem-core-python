import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from golem_core.core.events import Event


DEFAULT_LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "[%(asctime)s %(levelname)s %(name)s] %(message)s",
        },
    },
    "handlers": {"console": {"formatter": "default", "class": "logging.StreamHandler"}},
    "loggers": {
        "": {
            "level": "INFO",
            "handlers": [
                "console",
            ],
        },
        "golem_core": {
            "level": "INFO",
        },
        "golem_core.managers": {
            "level": "INFO",
        },
        "golem_core.managers.negotiation": {
            "level": "INFO",
        },
        "golem_core.managers.proposal": {
            "level": "INFO",
        },
    },
}


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
        golem.event_bus.listen(DefaultLogger().on_event)

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
        logger = logging.getLogger("golem_core")
        logger.setLevel(logging.DEBUG)

        format_ = "[%(asctime)s %(levelname)s %(name)s] %(message)s"
        formatter = _YagnaDatetimeFormatter(fmt=format_)

        file_handler = logging.FileHandler(filename=self._file_name, mode="w", encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)

        return logger

    async def on_event(self, event: "Event") -> None:
        """Handle event produced by :any:`EventBus.listen`."""
        self.logger.info(event)
