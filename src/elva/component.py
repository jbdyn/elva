"""
Module for generic asynchronous app component.
"""

import logging
from contextlib import AsyncExitStack
from enum import Flag
from typing import Iterable, Self

from anyio import (
    TASK_STATUS_IGNORED,
    BrokenResourceError,
    CancelScope,
    Lock,
    WouldBlock,
    create_memory_object_stream,
    create_task_group,
    get_cancelled_exc_class,
    sleep_forever,
)
from anyio.abc import TaskGroup, TaskStatus
from anyio.streams.memory import MemoryObjectReceiveStream

from elva.log import LOGGER_NAME


def create_component_state(
    name: str, additional_states: None | Iterable[str] = None
) -> Flag:
    """
    Create a [`Flag`][enum.Flag] enumeration with the default flags `NONE` and `RUNNING` for [`Component`s][elva.component.Component].

    Arguments:
        name: the states class name.
        additional_states: states to include next to the default ones.

    Returns:
        component states as flag enumeration.
    """
    states = ("NONE", "ACTIVE", "RUNNING")

    if additional_states is not None:
        states += tuple(additional_states)

    return Flag(name, states, start=0)


ComponentState = create_component_state("ComponentState")
"""The default component states."""


class Component:
    """
    Generic asynchronous app component class.

    This class features graceful shutdown alongside annotated logging.
    It is used for writing providers, stores, parsers, renderers etc.

    It supports explicit handling via the [`start`][elva.component.Component.start]
    and [`stop`][elva.component.Component.stop] method as well as the asynchronous
    context manager protocol.
    """

    _task_group: TaskGroup | None = None
    _start_lock: Lock | None = None

    log: logging.Logger
    """Logger instance to write logging messages to."""

    _subscribers: dict
    """Mapping of receiving streams to their respective sending stream over which to publish state changes."""

    def __new__(cls, *args: tuple, **kwargs: dict) -> Self:
        self = super().__new__(cls)
        name = LOGGER_NAME.get(self.__module__)
        self.log = logging.getLogger(f"{name}.{self.__class__.__name__}")

        # level is inherited from parent logger
        self.log.setLevel(logging.NOTSET)

        # setup empty subscriber mapping
        self._subscribers = dict()

        # set default state of every component
        self._state = self.states.NONE

        return self

    def __str__(self):
        return f"{self.__class__.__name__}"

    @property
    def states(self) -> ComponentState:
        """
        Enumeration class holding all states the component can have.
        """
        return ComponentState

    @property
    def state(self):
        """
        The current state of the component.
        """
        return self._state

    @state.setter
    def state(self, new: Flag):
        new = self.states(new)
        self._state = new
        self.log.info(f"set state to {new}")

    def subscribe(self) -> MemoryObjectReceiveStream:
        """
        Get an object to listen on for differences in component state.

        Returns:
            the receiving end of an asynchronous memory object stream emitting
            tuple of deleted and added states.
        """
        # create a stream with a defined maximum buffer size,
        # otherwise - with default of max_buffer_size=0 - sending would block
        send, recv = create_memory_object_stream[tuple[Flag, Flag]](
            max_buffer_size=8192
        )

        # set the receiving end as key so that it can easily be unsubscribed
        self._subscribers[recv] = send
        self.log.info(f"added subscriber {id(recv)}")

        return recv

    def unsubscribe(self, recv: MemoryObjectReceiveStream):
        """
        Close and remove the memory object stream from the mapping of subscribers.

        Arguments:
            recv: the receiving end of the memory object stream as returned by [`subscribe`][elva.component.Component.subscribe].
        """
        send = self._subscribers.pop(recv)
        send.close()
        self.log.info(f"removed subscriber {id(recv)}")

    def _change_state(self, from_state: Flag, to_state: Flag):
        """
        Replace a state with another state within the current component [`state`][elva.component.Component.state].

        The special state `NONE` can be used as an identity, i.e. no-op, flag.

        Arguments:
            from_state: the state to remove.
            to_state: the state to insert.
        """
        # no change in state
        if from_state == to_state:
            return

        # remove `from_state`, add `to_state`
        state = self.state & ~from_state | to_state

        # set the state from the component's states
        self.state = state

        if from_state != self.states.NONE:
            self.log.info(f"removed state {from_state}")

        if to_state != self.states.NONE:
            self.log.info(f"added state {to_state}")

        # copy to avoid exceptions due to set changes during iteration
        subs = self._subscribers.copy()

        # send the state diff to the subscribers
        for recv, send in subs.items():
            try:
                send.send_nowait((from_state, to_state))
                self.log.debug(f"sent state change to subscriber {id(recv)}")
            except (BrokenResourceError, WouldBlock):
                # either the send stream has a respective closed receive stream
                # or the stream buffer is full, so it is not in use either way
                # and we unsubscribe ourselves
                self.unsubscribe(recv)

    def close(self):
        """
        Run [`unsubscribe`][elva.component.Component.unsubscribe] from all subscriptions.
        """
        subs = self._subscribers.copy()
        for recv in subs:
            self.unsubscribe(recv)

    def __del__(self):
        # close subscriptions before deletion
        self.close()

    def _get_start_lock(self):
        if self._start_lock is None:
            self._start_lock = Lock()
        return self._start_lock

    async def __aenter__(self):
        if self._task_group is not None:
            raise RuntimeError(f"{self} already active")

        async with self._get_start_lock():
            # enter the asynchronous context and start the runner in it
            self._exit_stack = AsyncExitStack()
            await self._exit_stack.__aenter__()
            self._task_group = await self._exit_stack.enter_async_context(
                create_task_group()
            )

            self.log.info("starting")

            # add `ACTIVE` state
            self._change_state(self.states.NONE, self.states.ACTIVE)

            # start the main coroutine
            await self._task_group.start(self._run)

        return self

    async def __aexit__(self, exc_type, exc_value, exc_tb):
        await self.stop()
        return await self._exit_stack.__aexit__(exc_type, exc_value, exc_tb)

    async def _run(self, task_status: TaskStatus[None] = TASK_STATUS_IGNORED):
        # Handle `run` method gracefully

        # start runner and do a shielded cleanup on cancellation
        try:
            await self.before()

            # signal that the setup has finished
            task_status.started()
            self.log.info("started")

            # add `RUNNING` state
            self._change_state(self.states.NONE, self.states.RUNNING)

            await self.run()

            # keep the task running when `self.run()` has finished
            # so the cancellation exception can be always caught
            await sleep_forever()
        except get_cancelled_exc_class():
            self.log.info("stopping")
            with CancelScope(shield=True):
                await self.cleanup()

            self._task_group = None
            self.log.info("stopped")

            # change from current state to `NONE`
            self._change_state(self.state, self.states.NONE)

            # always re-raise a captured cancellation exception,
            # otherwise the behavior is undefined
            raise

    async def start(self, task_status: TaskStatus[None] = TASK_STATUS_IGNORED):
        """
        Start the component.

        Arguments:
            task_status: The status to set when the task has started.
        """
        if self._task_group is not None:
            raise RuntimeError(f"{self} already active")

        async with self._get_start_lock():
            async with create_task_group() as self._task_group:
                self.log.info("starting")

                # add `ACTIVE` state
                self._change_state(self.states.NONE, self.states.ACTIVE)

                # start the main coroutine
                await self._task_group.start(self._run)

                # signal that the coroutine has started
                task_status.started()

    async def stop(self):
        """
        Stop the component by cancelling all inner task groups.
        """
        if self._task_group is None:
            raise RuntimeError(f"{self} not active")

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
