"""
Module for generic asynchronous app component.
"""

import logging
from contextlib import AsyncExitStack

from anyio import (
    TASK_STATUS_IGNORED,
    CancelScope,
    Event,
    Lock,
    create_task_group,
    get_cancelled_exc_class,
    sleep_forever,
)
from anyio.abc import TaskGroup, TaskStatus

from elva.log import LOGGER_NAME


class Component:
    """
    Generic asynchronous app component class.

    This class features graceful shutdown alongside annotated logging.
    It is used for writing providers, stores, parsers, renderers etc.

    It supports explicit handling via the [`start`][elva.component.Component.start]
    and [`stop`][elva.component.Component.stop] method as well as the asynchronous
    context manager protocol.
    """

    _started: Event | None = None
    _stopped: Event | None = None
    _task_group: TaskGroup | None = None
    _start_lock: Lock | None = None

    log: logging.Logger
    """Logger instance to write logging messages to."""

    def __new__(cls, *args, **kwargs):
        self = super().__new__(cls)
        name = LOGGER_NAME.get(self.__module__)
        self.log = logging.getLogger(f"{name}.{self.__class__.__name__}")

        # level is inherited from parent logger
        self.log.setLevel(logging.NOTSET)
        return self

    def __str__(self):
        return f"{self.__class__.__name__}"

    @property
    def started(self) -> Event:
        """
        Event signaling that the component has been started, i.e. is initialized and running.
        """
        if self._started is None:
            self._started = Event()
        return self._started

    @property
    def stopped(self) -> Event:
        """
        Event signaling that the component has been stopped, i.e. deinitialized and not running.
        """
        if self._stopped is None:
            self._stopped = Event()
        return self._stopped

    def _get_start_lock(self):
        if self._start_lock is None:
            self._start_lock = Lock()
        return self._start_lock

    async def __aenter__(self):
        async with self._get_start_lock():
            if self._task_group is not None:
                raise RuntimeError(f"{self} already running")

            # enter the asynchronous context and start the runner in it
            self._exit_stack = AsyncExitStack()
            await self._exit_stack.__aenter__()
            self._task_group = await self._exit_stack.enter_async_context(
                create_task_group()
            )
            await self._task_group.start(self._run)

        return self

    async def __aexit__(self, exc_type, exc_value, exc_tb):
        await self.stop()
        return await self._exit_stack.__aexit__(exc_type, exc_value, exc_tb)

    async def _run(self, task_status):
        # Handle `run` method gracefully

        # start runner and do a shielded cleanup on cancellation
        try:
            await self.before()
            self.started.set()
            task_status.started()
            self.log.info("started")

            await self.run()

            # keep the task running when `self.run()` has finished
            # so the cancellation exception can be always caught
            await sleep_forever()
        except get_cancelled_exc_class():
            self.log.info("stopping")
            with CancelScope(shield=True):
                await self.cleanup()

            self.stopped.set()
            self._task_group = None
            self.log.info("stopped")

            # always re-raise a captured cancellation exception,
            # otherwise the behavior is undefined
            raise

    async def start(self, task_status: TaskStatus[None] = TASK_STATUS_IGNORED):
        """
        Start the component.

        Arguments:
            task_status: The status to set when the task has started.
        """
        self.log.info("starting")
        async with self._get_start_lock():
            if self._task_group is not None:
                raise RuntimeError(f"{self} already running")

            async with create_task_group() as self._task_group:
                await self._task_group.start(self._run)
                task_status.started()

    async def stop(self):
        """
        Stop the component by cancelling all inner task groups.
        """
        if self._task_group is None:
            raise RuntimeError(f"{self} not running")

        self._task_group.cancel_scope.cancel()
        self.log.debug("cancelled")

    async def before(self):
        """
        Hook to run before the component signals that is has been started.

        In here, one would define initializing steps necessary for the component to run.
        This method must return, otherwise the component will not set the
        [`started`][elva.component.Component.started] signal.

        It is defined as a no-op and supposed to be implemented in the inheriting class.
        """
        ...

    async def run(self):
        """
        Hook to run after the component signals that is has been started.

        In here, one would define the main functionality of the component.
        This method may run indefinitely or return.
        The component is kept running regardless.

        It is defined as a no-op and supposed to be implemented in the inheriting class.
        """
        ...

    async def cleanup(self):
        """
        Hook to run after the component's [`stop`][elva.component.Component.stop] method
        has been called and before it sets the [`stopped`][elva.component.Component.stopped] event.

        In here, one would define cleanup tasks such as closing connections.
        This method must return, otherwise the component will not set the
        [`stopped`][elva.component.Component.stopped] signal.

        It is defined as a no-op and supposed to be implemented in the inheriting class.
        """
        ...
