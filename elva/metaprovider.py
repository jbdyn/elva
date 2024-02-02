import anyio
from pycrdt import Doc
from pycrdt_websocket.yutils import (
    process_sync_message,
    read_message,
    YMessageType,
    YSyncMessageType,
    create_sync_step1_message,
    create_sync_step2_message,
    create_update_message,
    write_var_uint,
)
import asyncio
from anyio.abc import TaskGroup, TaskStatus
from pycrdt_websocket.websocket import Websocket
import websockets
import contextlib
import logging
from functools import partial
import sys
import importlib

log = logging.getLogger(__name__)
log_handler = logging.StreamHandler(sys.stdout)
log.addHandler(log_handler)
log.setLevel(logging.DEBUG)

uuid = str

class MetaProvider():
    def __init__(self, connection):
        self.connection = connection
        self.LOCAL_SOCKETS: dict[uuid, set[Websocket]] = dict()

    async def __aenter__(self):
        async with contextlib.AsyncExitStack() as exit_stack:
            tg = anyio.create_task_group()
            self.task_group = await exit_stack.enter_async_context(tg)
            self.exit_stack = exit_stack.pop_all()
           # for uuid, ydoc in self.ydocs.items():
           #     print(f"> observing YDoc {ydoc} with UUID {uuid}")
            self.task_group.start_soon(self.recv)
            #self.task_group.start_soon(self.sync_all) 
        return self

    async def __aexit__(self, exc_type, exc_value, exc_tb):
        self.task_group.cancel_scope.cancel()
        self.task_group = None
        return await self.exit_stack.__aexit__(exc_type, exc_value, exc_tb)

    def create_uuid_message(self, message, uuid):
        buuid = uuid.encode()
        return write_var_uint(len(buuid)) + buuid + message

    async def send(self, message, uuid):
        if len(self.LOCAL_SOCKETS[uuid]) > 1:
            await self.send_local(message, uuid)
        message = self.create_uuid_message(message, uuid)
        print(f"> sending {message} for {uuid}")
        await self.connection.send(message)

    def process_uuid_message(self, message):
        buuid = read_message(message)
        print(f"> binary uuid {buuid} extracted")
        return buuid.decode(), message[len(buuid) + 1:]

    async def recv(self):
        async for message in self.connection:
            print(f"> received {message}")
            uuid, message = self.process_uuid_message(message)
            print(f"> received {message} for {uuid}")
            await self.send_local(message, uuid)

    async def send_local(self, message, uuid):
        if uuid in self.LOCAL_SOCKETS.keys():
            for websocket in self.LOCAL_SOCKETS[uuid]:
                await websocket.send(message)
    
    async def serve(self, websocket: Websocket) -> None:
        if self.task_group is None:
            raise RuntimeError(
                "The WebsocketServer is not running: use `async with websocket_server:` or `await websocket_server.start()`"
            )

        #async with anyio.create_task_group() as tg:
        #    tg.start_soon(self._serve, websocket, tg)
        self.task_group.start_soon(self._serve, websocket, self.task_group)

    async def _serve(self, websocket: Websocket, tg: TaskGroup):
        uuid = websocket.path[1:]

        if uuid not in self.LOCAL_SOCKETS.keys():
            self.LOCAL_SOCKETS[uuid] = set()
        self.LOCAL_SOCKETS[uuid].add(websocket)

        try:
            async for message in websocket:
                await self.send(message, uuid)
        except Exception as e:
            log.error(e)
        finally:
            self.LOCAL_SOCKETS[uuid].remove(websocket)
            if len(self.LOCAL_SOCKETS[uuid]) == 0:
                self.LOCAL_SOCKETS.pop(uuid)

            await websocket.close()
            log.debug(f"closed connection {websocket}")
            log.debug(f"all clients: {self.LOCAL_SOCKETS}")
            tg.cancel_scope.cancel()

async def main():
    async with (
        websockets.connect("wss://example.com/sync/") as websocket_remote,
        MetaProvider(websocket_remote) as provider_meta,
        websockets.serve(provider_meta.serve, 'localhost', 8000) as server
    ):
        #await run('locahost', 8000, provider_meta)
        await asyncio.Future()

if __name__ == "__main__":
    try:
        #anyio.run(main, sys.argv[1])
        anyio.run(main)
    except KeyboardInterrupt:
        log.info("closing connections...")
        log.info("server stopped")
