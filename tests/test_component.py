import io
import logging
import multiprocessing
import os
import queue
import random
import signal
import time

import anyio
import pytest

from elva.component import Component
from elva.log import LOGGER_NAME, DefaultFormatter

pytestmark = pytest.mark.anyio


class Logger(Component):
    """Component logging to a buffer."""

    def __init__(self):
        self.buffer = list()

    async def before(self):
        self.buffer.append("before")

    async def run(self):
        self.buffer.append("run")

    async def cleanup(self):
        self.buffer.append("cleanup")


class WaitingLogger(Component):
    """Component logging to a buffer with some delay."""

    def __init__(self, seconds=0.5):
        self.buffer = list()
        self.seconds = seconds

    async def run(self):
        await anyio.sleep(self.seconds)
        self.buffer.append("run")

    async def cleanup(self):
        await anyio.sleep(self.seconds)
        self.buffer.append("cleanup")


class NamedLogger(Component):
    """Named component logging to a buffer."""

    def __init__(self, name, buffer):
        self.name = name
        self.buffer = buffer

    async def run(self):
        self.buffer.append((self.name, "run"))

    async def cleanup(self):
        self.buffer.append((self.name, "cleanup"))


class QueueLogger(Component):
    """Component logging to a queue."""

    def __init__(self, queue):
        self.queue = queue

    async def before(self):
        self.queue.put("before")

    async def run(self):
        self.queue.put("run")

    async def cleanup(self):
        self.queue.put("cleanup")


##
#
# TESTS
#


async def test_noop_component():
    """The Component base class is a no-op."""
    async with Component():
        pass


def test_component_repr():
    """A component's string representation is equal to its class name."""
    assert str(Component()) == "Component"

    class MyComp(Component):
        pass

    assert str(MyComp()) == "MyComp"


async def test_component_logging():
    """The component logger name is taken from the LOGGER_NAME context variable."""

    # setup base logger
    logger = logging.getLogger(__name__)
    file = io.StringIO()
    handler = logging.StreamHandler(file)
    handler.setFormatter(DefaultFormatter())
    logger.addHandler(handler)

    class TestLogger(Component):
        """Component logging its actions."""

        async def before(self):
            self.log.info("before")

        async def run(self):
            self.log.info("run")

        async def cleanup(self):
            self.log.info("cleanup")

    # __module__ is the default base name for component logger
    async with Component() as comp:
        assert comp.__module__ == "elva.component"
        assert comp.log.name == f"{comp.__module__}.Component"

    async with TestLogger() as test_logger:
        assert test_logger.__module__ == __name__ == "tests.test_component"
        assert test_logger.log.name == f"{test_logger.__module__}.TestLogger"

    # reset stream
    file.flush()
    file.truncate(0)
    file.seek(0)

    # set component logger name
    reset_token = LOGGER_NAME.set(__name__)

    # prepare expected contents
    test_logger_name = f"{__name__}.TestLogger"

    expected_info = (
        "starting",
        "before",
        "started",
        "run",
        "stopping",
        "cleanup",
        "stopped",
    )

    expected_debug = (
        "starting",
        "before",
        "started",
        "run",
        "cancelled",
        "stopping",
        "cleanup",
        "stopped",
    )

    for level, expected in zip(
        (logging.INFO, logging.DEBUG), (expected_info, expected_debug)
    ):
        # set the logging level
        # needs to be set to log something at all
        logger.setLevel(level)

        # go through one lifecycle of TestLogger component
        async with TestLogger() as test_logger:
            assert test_logger.log.name == test_logger_name

        # compare logs
        logs = file.getvalue()
        lines = logs.splitlines()

        assert len(lines) == len(expected)
        for expected, line in zip(expected, lines):
            assert expected in line
            assert test_logger_name in line

        # reset stream
        file.flush()
        file.truncate(0)
        file.seek(0)

    # reset LOGGER_NAME; just in case
    LOGGER_NAME.reset(reset_token)


async def test_unhandled_component_already_running():
    """A component raises an exception group when started twice via the async context manager."""
    with pytest.raises(ExceptionGroup):
        async with Component() as comp:
            async with comp:
                # will never be reached
                pass  # pragma: no cover


async def test_handled_component_already_running_context_manager():
    """A component includes a runtime error message when started twice via the async context manager."""
    with pytest.raises(RuntimeError) as excinfo:
        try:
            async with Component() as comp:
                async with comp:
                    # will never be reached
                    pass  # pragma: no cover
        except* RuntimeError as excgroup:
            for exc in excgroup.exceptions:
                raise exc

    # RuntimeError has no attribute `message`
    assert "already running" in repr(excinfo.value)


async def test_handled_component_already_running_method():
    """A component includes a runtime error message when started twice via its start method."""
    with pytest.raises(RuntimeError) as excinfo:
        try:
            async with Component() as comp:
                await comp.start()
        except* RuntimeError as excgroup:
            for exc in excgroup.exceptions:
                raise exc

    # RuntimeError has no attribute `message`
    assert "already running" in repr(excinfo.value)


async def test_handled_component_not_running_method():
    """A component includes a runtime error message when stopped twice via its stop method."""
    with pytest.raises(RuntimeError) as excinfo:
        try:
            comp = Component()
            await comp.stop()
        except* RuntimeError as excgroup:
            for exc in excgroup.exceptions:
                raise exc

    # RuntimeError has no attribute `message`
    assert "not running" in repr(excinfo.value)


async def test_start_stop_context_manager():
    """Components start and stop with the async context manager protocol."""

    # test Logger component
    async with Logger() as component:
        await component.started.wait()
        assert component.buffer == ["before", "run"]

    assert component.stopped.is_set()
    assert component.buffer == ["before", "run", "cleanup"]

    # test QueueLogger component
    q = queue.Queue()
    actions = list()
    async with QueueLogger(q) as component:
        await component.started.wait()
        i = 0
        while True:
            actions.append(q.get())
            i += 1
            if i > 1:
                break
        assert actions == ["before", "run"]

    assert component.stopped.is_set()
    actions.append(q.get())
    assert actions == ["before", "run", "cleanup"]

    # test WaitingLogger component
    async with WaitingLogger() as component:
        await component.started.wait()
        await anyio.sleep(component.seconds + 0.1)
        assert component.buffer == ["run"]

    assert component.stopped.is_set()
    assert component.buffer == ["run", "cleanup"]


async def test_start_stop_context_manager_nested():
    """Components start and stop in order of nested context."""

    buffer = list()
    async with NamedLogger(1, buffer=buffer):
        async with NamedLogger(2, buffer=buffer):
            async with NamedLogger(3, buffer=buffer):
                pass

    assert buffer == [
        (1, "run"),
        (2, "run"),
        (3, "run"),
        (3, "cleanup"),
        (2, "cleanup"),
        (1, "cleanup"),
    ]


async def test_start_stop_methods():
    """Components start and stop via methods."""

    component = Logger()

    async with anyio.create_task_group() as tg:
        await tg.start(component.start)
        await component.started.wait()
        assert component.buffer == ["before", "run"]
        await component.stop()
        await component.stopped.wait()
        assert component.buffer == ["before", "run", "cleanup"]


async def test_start_stop_methods_concurrent():
    """Components run concurrently."""

    buffer = list()
    num_comps = 5
    comps = [(i, NamedLogger(i, buffer=buffer)) for i in range(1, num_comps + 1)]

    events = list()

    async with anyio.create_task_group() as tg:
        random.shuffle(comps)
        for i, comp in comps:
            await tg.start(comp.start)
            events.append((i, "run"))

        random.shuffle(comps)
        for i, comp in comps:
            await comp.stop()
            await comp.stopped.wait()
            events.append((i, "cleanup"))

    assert buffer == events


async def test_start_stop_nested_concurrent_mixed():
    """Components start and stop concurrently in nested contexts."""

    buffer = list()
    cm = NamedLogger("cm", buffer=buffer)
    ccs = [NamedLogger(i, buffer=buffer) for i in range(1, 3)]

    async with cm:
        async with anyio.create_task_group() as tg:
            for cc in ccs:
                await tg.start(cc.start)
                await cc.stop()
                await cc.stopped.wait()

    assert buffer == [
        ("cm", "run"),
        (1, "run"),
        (1, "cleanup"),
        (2, "run"),
        (2, "cleanup"),
        ("cm", "cleanup"),
    ]


async def test_interrupt_with_method():
    """Components get interrupted with stop method."""

    async with WaitingLogger() as comp:
        await comp.started.wait()
        assert comp.buffer == []
        await comp.stop()
        assert comp.buffer == []

    assert comp.stopped.is_set()
    assert comp.buffer == ["cleanup"]


# needs to be defined here;
# avoid AttributeError about not getting locals
async def run(comp):
    async with anyio.create_task_group() as tg:
        await tg.start(comp.start)
        await anyio.sleep_forever()


def test_interrupt_by_signal():
    """Components get cancelled on SIGINT signal."""

    actions = list()

    # avoid DeprecationWarning using `os.fork()` internally
    # see https://docs.python.org/3/library/multiprocessing.html#multiprocessing.set_start_method
    #
    # also, avoids specifying the start method globally
    ctx = multiprocessing.get_context("spawn")

    # use a queue accessible over multiple processes
    q = ctx.Queue()
    comp = QueueLogger(queue=q)

    # spawn the process
    process = ctx.Process(target=anyio.run, args=(run, comp), name="interrupt")
    process.start()
    assert process.is_alive()

    # give the anyio.run and the QueueLogger component time to start
    time.sleep(0.5)

    # component should be running by now
    while True:
        try:
            actions.append(q.get(block=False))
        except queue.Empty:
            break

    # kill the process so that `pytest` won't get stuck after an AssertionError
    os.kill(process.pid, signal.SIGINT)

    assert actions == ["before", "run"]

    # fetch the cleanup action
    actions.append(q.get())

    assert actions == ["before", "run", "cleanup"]

    # wait until the process has stopped
    process.join()
    assert not process.is_alive()
