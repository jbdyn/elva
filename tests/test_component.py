import random
import signal
import threading

import anyio
import pytest

from elva.component import Component

pytestmark = pytest.mark.anyio


class Placeholder(Component):
    def __init__(self):
        self.placeholder = list()

    async def run(self):
        self.placeholder.append("run")

    async def cleanup(self):
        self.placeholder.append("cleanup")


class WaitingPlaceholder(Component):
    def __init__(self, seconds=0.5):
        self.placeholder = list()
        self.seconds = seconds

    async def run(self):
        await anyio.sleep(self.seconds)
        self.placeholder.append("run")

    async def cleanup(self):
        await anyio.sleep(self.seconds)
        self.placeholder.append("cleanup")


class NamedPlaceholder(Component):
    def __init__(self, name, seconds=None, placeholder=None):
        self.name = name
        if placeholder is None:
            placeholder = list()
        self.placeholder = placeholder
        self.seconds = seconds

    async def run(self):
        if self.seconds is not None:
            await anyio.sleep(self.seconds)
        self.placeholder.append((self.name, "run"))

    async def cleanup(self):
        if self.seconds is not None:
            await anyio.sleep(self.seconds)
        self.placeholder.append((self.name, "cleanup"))


#
## TESTS
#
async def test_start_stop_context_manager():
    async with Placeholder() as component:
        await component.started.wait()
        assert component.placeholder == ["run"]

    assert component.stopped.is_set()
    assert component.placeholder == ["run", "cleanup"]

    async with WaitingPlaceholder() as component:
        await component.started.wait()
        await anyio.sleep(component.seconds + 0.1)
        assert component.placeholder == ["run"]

    assert component.stopped.is_set()
    assert component.placeholder == ["run", "cleanup"]


async def test_start_stop_context_manager_nested():
    placeholder = list()
    async with NamedPlaceholder(1, placeholder=placeholder):
        async with NamedPlaceholder(2, placeholder=placeholder):
            async with NamedPlaceholder(3, placeholder=placeholder):
                pass

    assert placeholder == [
        (1, "run"),
        (2, "run"),
        (3, "run"),
        (3, "cleanup"),
        (2, "cleanup"),
        (1, "cleanup"),
    ]


async def test_start_stop_methods():
    component = Placeholder()

    async with anyio.create_task_group() as tg:
        await tg.start(component.start)
        await component.started.wait()
        assert component.placeholder == ["run"]
        await component.stop()
        await component.stopped.wait()
        assert component.placeholder == ["run", "cleanup"]


async def test_start_stop_methods_concurrent():
    placeholder = list()
    num_comps = 5
    comps = [
        (i, NamedPlaceholder(i, placeholder=placeholder))
        for i in range(1, num_comps + 1)
    ]

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

    assert placeholder == events


async def test_start_stop_nested_concurrent_mixed_1():
    placeholder = list()
    cm = NamedPlaceholder("cm", placeholder=placeholder)
    ccs = [NamedPlaceholder(i, placeholder=placeholder) for i in range(1, 3)]

    async with cm:
        async with anyio.create_task_group() as tg:
            for cc in ccs:
                await tg.start(cc.start)
                await cc.stop()
                await cc.stopped.wait()

    assert placeholder == [
        ("cm", "run"),
        (1, "run"),
        (1, "cleanup"),
        (2, "run"),
        (2, "cleanup"),
        ("cm", "cleanup"),
    ]


async def test_start_stop_nested_concurrent_mixed_2():
    placeholder = list()
    cm = NamedPlaceholder("cm", placeholder=placeholder)
    ccs = [NamedPlaceholder(i, placeholder=placeholder) for i in range(1, 3)]

    async with anyio.create_task_group() as tg:
        async with cm:
            for cc in ccs:
                await tg.start(cc.start)
                await cc.stop()
                await cc.stopped.wait()

    assert placeholder == [
        ("cm", "run"),
        (1, "run"),
        (1, "cleanup"),
        (2, "run"),
        (2, "cleanup"),
        ("cm", "cleanup"),
    ]


async def test_interrupt_with_method():
    async with WaitingPlaceholder() as comp:
        await comp.started.wait()
        assert comp.placeholder == []
        await comp.stop()
        assert comp.placeholder == []

    assert comp.stopped.is_set()
    assert comp.placeholder == ["cleanup"]


# TODO: test for SIGTERM behavior
async def interrupt_by_signal():
    placeholder = list()
    comp = NamedPlaceholder("thread", seconds=0.1, placeholder=placeholder)

    def worker(comp):
        async def run(comp):
            async with anyio.create_task_group() as tg:
                await tg.start(comp.start)

        anyio.run(run, comp)

    thread = threading.Thread(target=worker, args=[comp], name="interrupt")
    thread.start()
    assert thread.is_alive()
    await anyio.sleep(1)
    signal.pthread_kill(thread.ident, signal.SIGTERM)

    assert comp.placeholder == [("thread", "cleanup")]
