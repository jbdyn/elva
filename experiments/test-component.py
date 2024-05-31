import anyio
from elva.base import Component
from contextlib import AsyncExitStack
import elva.logging_config
import logging

from textual.app import App

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

class Test1(Component):
    async def run(self):
        log.debug("1: start running")
        try:
            while True:
                log.debug("1: running")
                await anyio.sleep(1)
        finally:
            log.debug("1: finally")

    async def cleanup(self):
        for i in (1, 2, 3):
            log.debug("1: cleanup")
            await anyio.sleep(0.5)
        log.debug("1: finished cleanup")

class Test2(Component):
    async def run(self):
        log.debug("2: start running")
        #try:
        #    while True:
        #        log.debug("2: running")
        #        await anyio.sleep(1)
        #finally:
        #    log.debug("2: finally")

    async def cleanup(self):
        for i in "abcdef":
            log.debug("2: cleanup")
            await anyio.sleep(0.5)
        log.debug("2: finished cleanup")

class Test3(Component):
    def __init__(self, dependency):
        self.dependency = dependency
        log.debug(self)
        log.debug(self.__repr__())


    async def run(self):
        async with anyio.create_task_group() as tg:
            await tg.start(self.dependency.start)

    async def cleanup(self):
        for i in "vwxyz":
            log.debug("3: cleanup")
            await anyio.sleep(0.5)
        log.debug("3: finished cleanup")


async def main1():
    test1 = Test1()
    test2 = Test2()
    # cancel scopes in parallel
    async with anyio.create_task_group() as tg:
        await tg.start(test1.start)
        await tg.start(test2.start)
        await anyio.sleep(2)
        tg.start_soon(test2.stop)
        tg.start_soon(test1.stop)

async def main2():
    # nesting context managers,
    # thus nesting cancel scopes,
    # thus executing cleanups sequentially
    async with Test2(), Test1():
        await anyio.sleep(2)

async def main3():
    test2 = Test2([Test1(), Test3()])
    test3 = Test3()

    async with anyio.create_task_group() as tg:
        await tg.start(test2.start)
        await tg.start(test3.start)
        await anyio.sleep(2)
        tg.start_soon(test3.stop)
        tg.start_soon(test2.stop)


async def main4():
    app = App()
    test1 = Test1()
    test2 = Test2()
    test3 = Test3(test2)
    async with anyio.create_task_group() as tg:
        #await tg.start(test1.start)
        await tg.start(test3.start)
        log.debug("> enter sleeping")
        await anyio.sleep(2)
        log.debug("> exit sleeping")
        #log.debug("> enter app")
        #await app.run_async()
        #log.debug("> exit app")
        tg.start_soon(test3.stop)
        #tg.start_soon(test1.stop)

async def main():
    log = logging.getLogger(__name__)
    try:
        await main4()
    except anyio.get_cancelled_exc_class():
        log.debug("exiting gracefully")

if __name__ == "__main__":
    anyio.run(main)
