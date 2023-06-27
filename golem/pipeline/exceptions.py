from golem.exceptions import GolemException


class InputStreamExhausted(GolemException):
    """Excepion used internally by pipeline-level components.

    This is something like StopAsyncIteration, but in context when StopAsyncIteration can't be used.
    All mid-level components understand & correctly process this exception, the only way to
    encounter it in non-chain code is to create a Chain that returns awaitables that can fail
    because of the input stream that did not return enough values.

    E.g. this will raise InputStreamExhausted with 0.64 chance::

        async def source():
            yield 1
            yield 2

        async def flaky_processing_function(val):
            from random import random
            if random() > 0.2:
                raise Exception("Ooops")

            return val

        async for awaitable_result in Chain(
            source(),
            Map(flaky_processing_function),
        ):
            print(await awaitable_result)
            break

    But if we add a Buffer in the end of the chain::

        async for result in Chain(
            source(),
            Map(flaky_processing_function),
            Buffer(),
        ):
            print(result)
            break

    then this exception will be handled by the Buffer (and we have 0.64 chance anything will be
    printed).

    """
