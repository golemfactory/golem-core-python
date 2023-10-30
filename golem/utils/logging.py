import contextvars
import inspect
import logging
from datetime import datetime, timezone
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, Sequence, Union

if TYPE_CHECKING:
    from golem.event_bus import Event


DEFAULT_LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "add_trace_id": {
            "()": "golem.utils.logging.AddTraceIdFilter",
        },
    },
    "formatters": {
        "default": {
            "format": "[%(asctime)s] [%(levelname)-7s] [%(traceid)s] "
            "[%(name)s:%(lineno)d] %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "filters": ["add_trace_id"],
        },
    },
    "root": {
        "level": "INFO",
        "handlers": [
            "console",
        ],
    },
    "loggers": {
        "asyncio": {
            "level": "INFO",
        },
        "golem": {
            "level": "INFO",
        },
        "golem.utils": {
            "level": "INFO",
        },
        "golem.managers": {
            "level": "INFO",
        },
        "golem.managers.payment": {
            "level": "INFO",
        },
        "golem.managers.network": {
            "level": "INFO",
        },
        "golem.managers.demand": {
            "level": "INFO",
        },
        "golem.managers.negotiation": {
            "level": "INFO",
        },
        "golem.managers.proposal": {
            "level": "INFO",
        },
        "golem.managers.agreement": {
            "level": "INFO",
        },
        "golem.managers.activity": {
            "level": "INFO",
        },
        "golem.managers.work": {
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


trace_id_var = contextvars.ContextVar("trace_id", default="root")


def get_trace_id_name(obj: Any, postfix: str) -> str:
    return f"{obj.__class__.__name__}-{id(obj)}-{postfix}"


class TraceSpan:
    def __init__(
        self,
        name: Optional[Union[str, Callable[[Any], str]]] = None,
        show_arguments: bool = False,
        show_results: bool = False,
        log_level: int = logging.DEBUG,
    ) -> None:
        self._name = name
        self._show_arguments = show_arguments
        self._show_results = show_results
        self._log_level = log_level

    def __call__(self, func):
        wrapper = self._async_wrapper if inspect.iscoroutinefunction(func) else self._sync_wrapper

        # TODO: partial instead of decorator()
        def decorator(*args, **kwargs):
            return wrapper(func, args, kwargs)

        return wraps(func)(decorator)

    def _get_span_name(self, func: Callable, args: Sequence, kwargs: Dict) -> str:
        if self._name is not None:
            return self._name(args[0]) if callable(self._name) else self._name

        # TODO: check type of func in different cases + contextmanager
        span_name = (
            func.__qualname__.split(">.")[-1] if self._is_instance_method(func) else func.__name__
        )

        if self._show_arguments:
            arguments = ", ".join(
                [
                    *[repr(a) for a in (args[1:] if self._is_instance_method(func) else args)],
                    *["{}={}".format(k, repr(v)) for (k, v) in kwargs.items()],
                ]
            )
            return f"Calling {span_name}({arguments})"

        return f"Calling {span_name}"

    def _get_logger(self, func: Callable, args: Sequence) -> logging.Logger:
        module_name = (
            args[0].__class__.__module__ if self._is_instance_method(func) else func.__module__
        )

        return logging.getLogger(module_name)

    def _is_instance_method(self, func: Callable) -> bool:
        return inspect.isfunction(func) and func.__name__ != func.__qualname__.split(">.")[-1]

    def _sync_wrapper(self, func: Callable, args: Sequence, kwargs: Dict) -> Any:
        span_name = self._get_span_name(func, args, kwargs)
        logger = self._get_logger(func, args)

        logger.log(self._log_level, "%s...", span_name)

        try:
            result = func(*args, **kwargs)
        except Exception as e:
            logger.log(self._log_level, "%s failed with `%s`", span_name, e)
            raise

        if self._show_results:
            logger.log(self._log_level, "%s done with `%s`", span_name, result)
        else:
            logger.log(self._log_level, "%s done", span_name)

        return result

    async def _async_wrapper(self, func: Callable, args: Sequence, kwargs: Dict) -> Any:
        span_name = self._get_span_name(func, args, kwargs)
        logger = self._get_logger(func, args)

        logger.log(self._log_level, "%s...", span_name)

        try:
            result = await func(*args, **kwargs)
        except Exception as e:
            logger.log(self._log_level, "%s failed with `%s`", span_name, e)
            raise

        if self._show_results:
            logger.log(self._log_level, "%s done with `%s`", span_name, result)
        else:
            logger.log(self._log_level, "%s done", span_name)

        return result


trace_span = TraceSpan


class AddTraceIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.traceid = trace_id_var.get()

        return super().filter(record)
