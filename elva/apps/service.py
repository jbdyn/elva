import logging
import pickle
import sys
from logging import FileHandler, getLogger
from pathlib import Path, PurePosixPath

import anyio
import click
import websockets
from pycrdt_websocket.websocket import Websocket

from elva.cli import LOG_NAME
from elva.log import DefaultFormatter
from elva.protocol import ElvaMessage
from elva.provider import WebsocketConnection

#
UUID = str
SYNC_PATH = PurePosixPath("/sync")
LOG_PATH = PurePosixPath("/log")


class WebsocketMetaProvider(WebsocketConnection):
    LOCAL_SOCKETS: dict[UUID, set[Websocket]]

    def __init__(self, uri):
        super().__init__(uri)
        self.log.setLevel(logging.DEBUG)
        self.LOCAL_SOCKETS = dict()

    async def on_recv(self, message):
        uuid, message = self.process_uuid_message(message)
        self.log.debug(f"< [{uuid}] received from remote to local: {message}")
        await self._send(message, uuid, None)

    def create_uuid_message(self, message, uuid):
        encoded_uuid, _ = ElvaMessage.ID.encode(uuid.encode())
        return encoded_uuid + message

    async def _send(self, message, uuid, origin_ws: Websocket | None = None) -> None:
        if origin_ws is not None:
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

    async def _send_to_remote(
        self, message: str, uuid: UUID, origin_ws: Websocket | None, origin_name: str
    ):
        # send message to self.remote
        message = self.create_uuid_message(message, uuid)
        self.log.debug(f"> [{uuid}] sending from {origin_name} to remote: {message}")
        await self.send(message)

    async def _send_to_local(
        self, message: str, uuid: UUID, origin_ws: Websocket | None, origin_name: str
    ):
        # check if any local client subscribed to the uuid
        if uuid in self.LOCAL_SOCKETS.keys():
            # go through all subscribed websockets
            for websocket in self.LOCAL_SOCKETS[uuid]:
                # don't send message back to it's origin
                if websocket == origin_ws:
                    self.log.debug(
                        f"/ [{uuid}] not sending message back to sender {get_websocket_identifier(websocket)}: {message}"
                    )
                    continue
                self.log.debug(
                    f"> [{uuid}] sending from {origin_name} to {get_websocket_identifier(websocket)}: {message}"
                )
                await websocket.send(message)
        else:
            self.log.info(f"  [{uuid}] no local recipient found for message: {message}")

    def process_uuid_message(self, message: bytes) -> tuple[UUID, str]:
        uuid, length = ElvaMessage.ID.decode(message)
        self.log.debug(f"  uuid extracted: {uuid}")
        return uuid.decode(), message[length:]

    async def serve(self, local: Websocket):
        path = PurePosixPath(local.path)
        if path.is_relative_to(SYNC_PATH):
            uuid = str(strip_root(path, SYNC_PATH))
            await self._send_from_local(local, uuid)
        elif path.is_relative_to(LOG_PATH):
            log_path = chroot(path, LOG_PATH)
            self.log.info(f"+ opening logging connection for {log_path}")
            await self._log(local, Path(log_path))

    async def _send_from_local(self, local: Websocket, uuid):
        ws_id = get_websocket_identifier(local)
        # uuid = get_uuid_from_local_websocket(local)
        self.log.debug(f"+ [{uuid}] local {ws_id} joined")

        # add websocket to set for uuid if  set does not exist create it
        if uuid not in self.LOCAL_SOCKETS.keys():
            self.LOCAL_SOCKETS[uuid] = set()
        self.LOCAL_SOCKETS[uuid].add(local)

        # listen for messages from local client and relay them
        try:
            async for message in local:
                self.log.debug(f"< [{uuid}] received from {ws_id}: {message}")
                await self._send(message, uuid, local)
        except Exception as e:
            self.log.error(e)
        finally:
            # after connection ended, remove webscoket from list
            self.LOCAL_SOCKETS[uuid].remove(local)
            if len(self.LOCAL_SOCKETS[uuid]) == 0:
                self.LOCAL_SOCKETS.pop(uuid)

            await local.close()
            self.log.debug(f"- closed connection {ws_id}")
            self.log.debug(f"  all clients: {self.LOCAL_SOCKETS}")

    async def _log(self, local, log_path):
        if log_path.is_dir():
            log_path /= LOG_NAME

        if not log_path.parent.exists():
            self.log.warning(
                f"- closing logging connection. No such directory {log_path.parent}"
            )
            await local.close()
            return

        logger = logging.getLogger(str(log_path))

        if not logger.hasHandlers():
            file_handler = FileHandler(log_path)
            file_handler.setFormatter(DefaultFormatter())
            logger.addHandler(file_handler)

        async for data in local:
            obj = pickle.loads(data)
            record = logging.makeLogRecord(obj)
            logger.handle(record)

        self.log.info("- closing logging connection")
        await local.close()


def strip_root(path, root):
    if path.is_relative_to(root):
        len_root = len(root.parts)
        return PurePosixPath(*path.parts[len_root:])
    else:
        return path


def chroot(path, root):
    if path.is_relative_to(root):
        len_root = len(root.parts)
        parts = ("/",) + path.parts[len_root:]
        return PurePosixPath(*parts)
    else:
        return path


def get_websocket_identifier(websocket: Websocket) -> str:
    # use memory address of websocket connection as identifier
    return hex(id(websocket))


def get_uuid_from_local_websocket(websocket: Websocket) -> UUID:
    # get room id (uuid) from websocketpath without the leading "/"
    return websocket.path[1:]


async def run(
    remote_websocket_server: str,
    local_websocket_host: str,
    local_websocket_port: int,
):
    server = WebsocketMetaProvider(remote_websocket_server)

    async with anyio.create_task_group() as tg:
        await tg.start(server.start)
        async with websockets.serve(
            server.serve, local_websocket_host, local_websocket_port
        ):
            await anyio.sleep_forever()


@click.command()
@click.pass_context
@click.argument("host", default="localhost")
@click.argument("port", default=8000)
def cli(ctx: click.Context, host, port):
    """local meta provider"""

    log = getLogger(__name__)
    log_handler = logging.StreamHandler(sys.stdout)
    log_handler.setFormatter(DefaultFormatter())
    log.addHandler(log_handler)
    log.setLevel(logging.DEBUG)

    try:
        anyio.run(run, ctx.obj["server"], host, port)
    except KeyboardInterrupt:
        log.info("service stopped")


if __name__ == "__main__":
    cli()
