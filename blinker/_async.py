import asyncio

from blinker.base import Signal


try:  # for Python3.7+
    create_task = asyncio.create_task
except AttributeError:  # for versions prior to Python3.7
    create_task = asyncio.ensure_future


async def _wrap_plain_value(value):
    """Pass through a coroutine 'value' or wrap a plain value"""
    if asyncio.iscoroutine(value):
        value = await value
    return value


def send_async(self, *sender, **kwargs):
    return [(receiver, create_task(_wrap_plain_value(value)))
            for receiver, value
            in self.send(*sender, **kwargs)]


send_async.__doc__ = Signal.send_async.__doc__
Signal.send_async = send_async
