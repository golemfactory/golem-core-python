import asyncio
import logging

import pytest

from golem.utils.logging import AddTraceIdFilter, trace_id_var, trace_span


def test_trace_span_on_standalone_function(caplog):
    caplog.set_level(logging.DEBUG)

    @trace_span()
    def foobar(a):
        return a

    value = "foobar"
    assert foobar(value) == value

    assert caplog.record_tuples == [
        ("tests.unit.utils.test_logging", logging.DEBUG, "Calling foobar..."),
        ("tests.unit.utils.test_logging", logging.DEBUG, "Calling foobar done"),
    ]


def test_trace_span_on_nested_function(caplog):
    caplog.set_level(logging.DEBUG)

    def foo(a):
        @trace_span()
        def bar(b):
            return b

        return bar(a)

    value = "foobar"
    assert foo(value) == value

    assert caplog.record_tuples == [
        ("tests.unit.utils.test_logging", logging.DEBUG, "Calling bar..."),
        ("tests.unit.utils.test_logging", logging.DEBUG, "Calling bar done"),
    ]


def test_trace_span_with_results(caplog):
    caplog.set_level(logging.DEBUG)

    @trace_span(show_results=True)
    def foobar(a):
        return a

    value = "foo"
    assert foobar(value) == value

    assert caplog.record_tuples == [
        ("tests.unit.utils.test_logging", logging.DEBUG, "Calling foobar..."),
        ("tests.unit.utils.test_logging", logging.DEBUG, f"Calling foobar done with `{value}`"),
    ]


def test_trace_span_with_exception(caplog):
    caplog.set_level(logging.DEBUG)

    exc_message = "some exception message"

    @trace_span()
    def foobar():
        raise Exception(exc_message)

    with pytest.raises(Exception, match=exc_message) as exc_info:
        foobar()

    assert caplog.record_tuples == [
        ("tests.unit.utils.test_logging", logging.DEBUG, "Calling foobar..."),
        (
            "tests.unit.utils.test_logging",
            logging.DEBUG,
            f"Calling foobar failed with `{exc_info.value}`",
        ),
    ]


def test_trace_span_on_async_function(caplog):
    caplog.set_level(logging.DEBUG, logger="tests.unit.utils.test_logging")

    @trace_span()
    async def foobar(a):
        return a

    value = "foobar"
    assert asyncio.run(foobar(value)) == value

    assert caplog.record_tuples == [
        ("tests.unit.utils.test_logging", logging.DEBUG, "Calling foobar..."),
        ("tests.unit.utils.test_logging", logging.DEBUG, "Calling foobar done"),
    ]


def test_trace_span_on_async_function_with_result(caplog):
    caplog.set_level(logging.DEBUG, logger="tests.unit.utils.test_logging")

    @trace_span(show_results=True)
    async def foobar(a):
        return a

    value = "foobar"
    assert asyncio.run(foobar(value)) == value

    assert caplog.record_tuples == [
        ("tests.unit.utils.test_logging", logging.DEBUG, "Calling foobar..."),
        ("tests.unit.utils.test_logging", logging.DEBUG, f"Calling foobar done with `{value}`"),
    ]


def test_trace_span_on_async_function_with_custom_name(caplog):
    caplog.set_level(logging.DEBUG, logger="tests.unit.utils.test_logging")
    custom_name = "custom_name"

    @trace_span(name=custom_name)
    async def foobar(a):
        return a

    value = "foobar"
    assert asyncio.run(foobar(value)) == value

    assert caplog.record_tuples == [
        ("tests.unit.utils.test_logging", logging.DEBUG, f"{custom_name}..."),
        ("tests.unit.utils.test_logging", logging.DEBUG, f"{custom_name} done"),
    ]


def test_trace_span_on_async_function_with_exception(caplog):
    caplog.set_level(logging.DEBUG, logger="tests.unit.utils.test_logging")
    exc_message = "some exception message"

    @trace_span()
    async def foobar():
        raise Exception(exc_message)

    with pytest.raises(Exception, match=exc_message) as exc_info:
        asyncio.run(foobar())

    assert caplog.record_tuples == [
        ("tests.unit.utils.test_logging", logging.DEBUG, "Calling foobar..."),
        (
            "tests.unit.utils.test_logging",
            logging.DEBUG,
            f"Calling foobar failed with `{exc_info.value}`",
        ),
    ]


def test_trace_span_on_async_function_with_log_level(caplog):
    caplog.set_level(logging.DEBUG, logger="tests.unit.utils.test_logging")
    log_level = logging.ERROR

    @trace_span(log_level=log_level)
    async def foobar(a):
        return a

    value = "foobar"
    assert asyncio.run(foobar(value)) == value

    assert caplog.record_tuples == [
        ("tests.unit.utils.test_logging", log_level, "Calling foobar..."),
        ("tests.unit.utils.test_logging", log_level, "Calling foobar done"),
    ]


def test_trace_span_on_method(caplog):
    caplog.set_level(logging.DEBUG)

    class Foo:
        @trace_span()
        def bar(self, a):
            return a

    value = "foobar"
    assert Foo().bar(value) == value

    assert caplog.record_tuples == [
        ("tests.unit.utils.test_logging", logging.DEBUG, "Calling Foo.bar..."),
        ("tests.unit.utils.test_logging", logging.DEBUG, "Calling Foo.bar done"),
    ]


def test_trace_span_with_custom_name(caplog):
    caplog.set_level(logging.DEBUG)
    custom_name = "custom-name"

    @trace_span(name=custom_name)
    def foobar(a):
        return a

    value = "foobar"
    assert foobar(value) == value

    assert caplog.record_tuples == [
        ("tests.unit.utils.test_logging", logging.DEBUG, f"{custom_name}..."),
        ("tests.unit.utils.test_logging", logging.DEBUG, f"{custom_name} done"),
    ]


def test_trace_span_with_log_level(caplog):
    caplog.set_level(logging.DEBUG)
    log_level = logging.ERROR

    @trace_span(log_level=log_level)
    def foobar(a):
        return a

    value = "foobar"
    assert foobar(value) == value

    assert caplog.record_tuples == [
        ("tests.unit.utils.test_logging", log_level, "Calling foobar..."),
        ("tests.unit.utils.test_logging", log_level, "Calling foobar done"),
    ]


def test_trace_span_with_arguments(caplog):
    caplog.set_level(logging.DEBUG)

    @trace_span(show_arguments=True)
    def foobar(a, b, c=None, d=None):
        return a

    a = "value_a"
    b = "value_b"
    c = "value_c"
    assert foobar(a, b, c=c) == a

    assert caplog.record_tuples == [
        (
            "tests.unit.utils.test_logging",
            logging.DEBUG,
            f"Calling foobar({repr(a)}, {repr(b)}, c={repr(c)})...",
        ),
        (
            "tests.unit.utils.test_logging",
            logging.DEBUG,
            f"Calling foobar({repr(a)}, {repr(b)}, c={repr(c)}) done",
        ),
    ]


def test_trace_id_filter(caplog):
    caplog.set_level(logging.DEBUG)
    trace_id_name = "custom-trace-id"
    logger_name = "logger_name"

    logger = logging.getLogger(logger_name)
    logger.addFilter(AddTraceIdFilter())

    logger.debug("log1")

    trace_id_var.set(trace_id_name)

    logger.debug("log2")

    assert caplog.record_tuples == [
        (logger_name, logging.DEBUG, "log1"),
        (logger_name, logging.DEBUG, "log2"),
    ]
    assert [getattr(rec, "traceid") for rec in caplog.records] == ["root", trace_id_name]
