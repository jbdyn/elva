import asyncio
import contextlib
import logging
import sys
from logging import Logger, getLogger

import anyio
import click
import websockets
from anyio.abc import TaskGroup
from pycrdt import read_message, write_var_uint
from pycrdt_websocket.websocket import Websocket
from websockets import WebSocketClientProtocol as WebSocketClient
from websockets import connect

# 
UUID = str

class MetaProvider():

    remote_connection: WebSocketClient
    LOCAL_SOCKETS: dict[UUID, set[Websocket]]
    log: Logger

    def __init__(self, remote_connection: WebSocketClient, log: Logger | None = None):
        self.remote_connection = remote_connection
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


    async def send(self, message, uuid, origin_ws: Websocket|None = None) -> None:

        if origin_ws != None:
            # if message comes from a local client (origin_ws != None)
            # send to other local clients if they exist and remote 

            origin_name = get_websocket_identifier(origin_ws)

            await self._send_to_local(message, uuid, origin_ws, origin_name)
            await self._send_to_remote(message, uuid, origin_ws, origin_name)
        else:
            # if message comes from remote (origin_ws == None)
            # only send to local clients
            
            origin_name = "remote"

            await self._send_to_local(message, uuid, origin_ws, origin_name)
        
    async def _send_to_remote(self, message: str, uuid: UUID, origin_ws: Websocket|None, origin_name: str):
        # send message to self.remote_connection 
        message = self.create_uuid_message(message, uuid)
        self.log.debug(f"> [{uuid}] sending from {origin_name} to remote: {message}")
        await self.remote_connection.send(message)

    async def _send_to_local(self, message: str, uuid: UUID, origin_ws: Websocket|None, origin_name: str):
        # check if any local client subscribed to the uuid
        if uuid in self.LOCAL_SOCKETS.keys():
           # go through all subscribed websockets 
            for websocket in self.LOCAL_SOCKETS[uuid]:
                # don't send message back to it's origin
                if websocket == origin_ws:
                    self.log.debug(f"> [{uuid}] not sending message back to sender: {message}")
                    continue
                self.log.debug(f"> [{uuid}] sending from {origin_name} to {get_websocket_identifier(websocket)}: {message}")
                await websocket.send(message)
        else:
            self.log.debug(f"> [{uuid}] no local recipient found for message: {message}")
    
    def process_uuid_message(self, message: bytes) -> tuple[UUID, str]:
        buuid = read_message(message)
        self.log.debug(f"# binary uuid extracted: {buuid}")
        return buuid.decode(), message[len(buuid) + 1:]

    async def recv(self):
        # listen for incomming messages from remote
        async for message in self.remote_connection:
            uuid, message = self.process_uuid_message(message)
            self.log.debug(f"< [{uuid}] received from remote to local: {message}")
            await self.send(message, uuid, None)

    async def serve(self, websocket: Websocket) -> None:
        # wrapper function called for every local connection, to make sure task_group exists

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

        # listen for messages from local client and relay them 
        try:
            async for message in websocket:
                self.log.debug(f"< [{uuid}] received from {ws_id}: {message}")
                await self.send(message, uuid, websocket)
        except Exception as e:
            self.log.error(e)
        finally:
            # after connection ended, remove webscoket from list
            self.LOCAL_SOCKETS[uuid].remove(websocket)
            if len(self.LOCAL_SOCKETS[uuid]) == 0:
                self.LOCAL_SOCKETS.pop(uuid)

            await websocket.close()
            self.log.debug(f"- closed connection {ws_id}")
            self.log.debug(f"all clients: {self.LOCAL_SOCKETS}")
            #tg.cancel_scope.cancel()

def get_websocket_identifier(websocket: Websocket) -> str:
    # use memory address of websocket connection as identifier
    return hex(id(websocket))

def get_uuid_from_local_websocket(websocket: Websocket) -> UUID:
    # get room id (uuid) from websocketpath without the leading "/"
    return websocket.path[1:]

async def run(log:Logger|None = None,
              remote_websocket_server:str ="wss://example.com/sync/",
              local_websocket_host:str ="localhost",
              local_websocket_port:int =8000,
              ):
    async with (
        websockets.connect(remote_websocket_server) as websocket_remote,
        MetaProvider(websocket_remote, log=log) as metaprovider,
        websockets.serve(metaprovider.serve, local_websocket_host, local_websocket_port)
    ):
        await asyncio.Future()


@click.command()
@click.pass_context
@click.argument(
    "host",
    default="localhost"
)
@click.argument(
    "port",
    default=8000
)
def cli(ctx: click.Context, host, port):
    """local meta provider"""

    log = getLogger(__name__)
    log_handler = logging.StreamHandler(sys.stdout)
    log.addHandler(log_handler)
    log.setLevel(logging.DEBUG)

    try:
        anyio.run(run, log, ctx.obj['server'], host, port)
    except KeyboardInterrupt:
        log.info("server stopped")

if __name__ == "__main__":
    cli()
