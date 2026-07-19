import asyncio
from functools import wraps
from loguru import logger

def loop(seconds: float, name=None):
    """
    A decorator that runs a function in an infinite loop with a specified delay.

    The decorated function is run every `seconds` seconds. The loop can be
    started and stopped using the `start` and `stop` methods of the
    returned object.

    :param seconds: The delay between calls to the decorated function.
    :type seconds: float
    :return: A class with `start` and `stop` methods.
    :rtype: Loop
    """
    def decorator(func):
        class Loop:
            def __init__(self):
                """
                Initialize the Loop object.

                Sets the task to None.
                """
                self.task = None
                self.name = name if name else func.__name__

            async def _runner(self, *a, **kw):
                """
                Run the decorated function in an infinite loop with a specified delay.

                The decorated function is run every `seconds` seconds. The loop can be
                started and stopped using the `start` and `stop` methods of the
                returned object.

                :param seconds: The delay between calls to the decorated function.
                :type seconds: float
                :return: None
                :rtype: NoneType
                """
                try:
                    logger.debug(f"Loop {self.name} started with a delay of {seconds} seconds...")
                    while True:
                        await func(*a, **kw)
                        await asyncio.sleep(seconds)
                except asyncio.CancelledError:
                    pass

            async def start(self, *a, **kw):
                """
                Start the loop.

                If the loop is not already running, this method creates a task that
                runs the decorated function in an infinite loop with a specified delay.

                :param *a: The positional arguments to pass to the decorated function.
                :param **kw: The keyword arguments to pass to the decorated function.
                :return: None
                :rtype: NoneType
                """
                if not self.task:
                    logger.debug(f"Starting loop {self.name}...")
                    self.task = asyncio.create_task(self._runner(*a, **kw))

            async def stop(self):
                """
                Stop the loop.

                If the loop is running, this method cancels the task that runs the
                decorated function and waits for the task to finish before setting the
                task to None.

                :return: None
                :rtype: NoneType
                """
                if self.task:
                    logger.debug(f"Stopping loop {self.name}...")
                    self.task.cancel()
                    try:
                        await self.task
                    except asyncio.CancelledError:
                        pass
                    self.task = None

        return Loop()

    return decorator
