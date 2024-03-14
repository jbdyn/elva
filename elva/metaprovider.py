import anyio
import asyncio
from anyio.abc import TaskGroup
from pycrdt_websocket.yutils import (
    read_message,
    write_var_uint,
)
from pycrdt_websocket.websocket import Websocket
import websockets
from websockets import connect, WebSocketClientProtocol as WebSocketClient
import contextlib
import logging
from logging import Logger, getLogger
import sys

# 
UUID = str

class MetaProvider():

    connection: WebSocketClient
    LOCAL_SOCKETS: dict[UUID, set[Websocket]]
    log: Logger

    def __init__(self, connection: WebSocketClient, log: Logger | None = None):
        self.connection = connection
        self.log = log or getLogger(__name__)
        self.LOCAL_SOCKETS = dict()

    async def __aenter__(self):
        async with contextlib.AsyncExitStack() as exit_stack:
            self.log.debug("entered context with exit stack")
            tg = anyio.create_task_group()
            self.log.debug("created taskgroup")
            self.task_group = await exit_stack.enter_async_context(tg)
            self.log.debug("added taskgroup to exit stack")
            self.exit_stack = exit_stack.pop_all()
            self.task_group.start_soon(self.recv)
        
        return self

    async def __aexit__(self, exc_type, exc_value, exc_tb):
        self.log.debug("exiting context")
        self.task_group.cancel_scope.cancel()
        self.log.debug("canceled taskgroup")
        self.task_group = None
        self.log.debug("exiting...")
        return await self.exit_stack.__aexit__(exc_type, exc_value, exc_tb)

    def create_uuid_message(self, message, uuid):
        buuid = uuid.encode()
        return write_var_uint(len(buuid)) + buuid + message

    async def send(self, message, uuid, sending: Websocket=None):
        await self.send_local(message, uuid, sending)
        message = self.create_uuid_message(message, uuid)
        self.log.debug(f"> [{uuid}] sending from {get_websocket_identifier(sending)} to remote: {message}")
        await self.connection.send(message)

    async def send_local(self, message, uuid, sending: Websocket|None=None):
        if uuid in self.LOCAL_SOCKETS.keys():
            for websocket in self.LOCAL_SOCKETS[uuid]:
                if websocket == sending:
                    self.log.debug(f"> [{uuid}] not sending message back to sender: {message}")
                    continue
                sender = "remote"
                if sending != None:
                    sender = f"{get_websocket_identifier(sending)}"
                self.log.debug(f"> [{uuid}] sending from {sender} to {get_websocket_identifier(websocket)}: {message}")
                await websocket.send(message)
        else:
            self.log.debug(f"> [{uuid}] no local recipient found for message: {message}")
    
    def process_uuid_message(self, message):
        buuid = read_message(message)
        self.log.debug(f"# binary uuid extracted: {buuid}")
        return buuid.decode(), message[len(buuid) + 1:]

    async def recv(self):
        async for message in self.connection:
            uuid, message = self.process_uuid_message(message)
            self.log.debug(f"< [{uuid}] received from remote to local: {message}")
            await self.send_local(message, uuid, None)

    async def serve(self, websocket: Websocket) -> None:
        if self.task_group is None:
            raise RuntimeError(
                "The WebsocketServer is not running: use `async with websocket_server:` or `await websocket_server.start()`"
            )

        await self._serve(websocket, self.task_group)

    async def _serve(self, websocket: Websocket, tg: TaskGroup):

        ws_id = get_websocket_identifier(websocket)
        uuid = get_uuid_from_local_websocket(websocket)
        self.log.debug(f"+ [{uuid}] local {ws_id} joined")

        # add websocket to set for uuid if  set does not exist create it
        if uuid not in self.LOCAL_SOCKETS.keys():
            self.LOCAL_SOCKETS[uuid] = set()
        self.LOCAL_SOCKETS[uuid].add(websocket)

        # 
        try:
            async for message in websocket:
                self.log.debug(f"< [{uuid}] received from {ws_id}: {message}")
                await self.send(message, uuid, websocket)
        except Exception as e:
            log.error(e)
        finally:
            self.LOCAL_SOCKETS[uuid].remove(websocket)
            if len(self.LOCAL_SOCKETS[uuid]) == 0:
                self.LOCAL_SOCKETS.pop(uuid)

            await websocket.close()
            log.debug(f"- closed connection {ws_id}")
            log.debug(f"all clients: {self.LOCAL_SOCKETS}")
            #tg.cancel_scope.cancel()

def get_websocket_identifier(websocket: Websocket) -> str:
    # use memory address of websocket connection as identifier
    return hex(id(websocket))

def get_uuid_from_local_websocket(websocket: Websocket) -> UUID:
    # get room id (uuid) from websocketpath without the leading "/"
    return websocket.path[1:]

async def main(log: Logger | None = None):
    async with (
        websockets.connect("wss://example.com/sync/") as websocket_remote,
        MetaProvider(websocket_remote) as metaprovider,
        websockets.serve(metaprovider.serve, 'localhost', 8000)
    ):
        await asyncio.Future()

if __name__ == "__main__":
    log = getLogger(__name__)
    log_handler = logging.StreamHandler(sys.stdout)
    log.addHandler(log_handler)
    log.setLevel(logging.DEBUG)
    try:
        anyio.run(main, log)
    except KeyboardInterrupt:
        log.info("server stopped")
