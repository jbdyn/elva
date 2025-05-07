"""
ELVA local service app.
"""

import logging
import sys
from http import HTTPStatus
from logging import getLogger
from urllib.parse import urlparse

import anyio
import click
import websockets
import websockets.exceptions as wsexc
from pycrdt_websocket.websocket import Websocket
from websockets.datastructures import Headers, HeadersLike
from websockets.typing import StatusLike

from elva.auth import basic_authorization_header
from elva.log import LOGGER_NAME, DefaultFormatter
from elva.protocol import ElvaMessage
from elva.provider import WebsocketConnection
from elva.utils import gather_context_information

UUID = str

log = getLogger(__name__)


def missing_identifier(
    path: str, request: Headers
) -> tuple[StatusLike, HeadersLike, bytes] | None:
    """
    Check a request for a missing Y document identifier.

    Arguments:
        path: the path of the request.
        request: the request header object.

    Returns:
        `None` to continue the request normally or a tuple with cancel information.
    """
    if path[1:] == "":
        return HTTPStatus.FORBIDDEN, {}, b""


class WebsocketMetaProvider(WebsocketConnection):
    """
    Broker routing Y updates from and to local and remote connections.
    """

    LOCAL_SOCKETS: dict[UUID, set[Websocket]]
    """Mapping of Y document identifiers to their corresponding set of websocket connections."""

    def __init__(self, user: str, password: str, uri: str):
        """
        Arguments:
            user: the user name to login with.
            password: the password to login with.
            uri: the URI to connect to remotely.
        """
        super().__init__(uri)
        self.user = user
        self.password = password
        self.tried_once = False
        self.LOCAL_SOCKETS = dict()

    async def on_recv(self, message: bytes):
        """
        Hook called on receiving data from remote.

        This method routes messages to local connections.

        Arguments:
            message: the received message.
        """
        uuid, message = self.process_uuid_message(message)
        self.log.debug(f"< [{uuid}] received from remote to local: {message}")
        await self._send(message, uuid, None)

    def create_uuid_message(self, message: bytes, uuid: str) -> bytes:
        """
        Create a message with a UUID message prepended.

        Arguments:
            message: the payload to attach to the UUID message.
            uuid: the UUID to prepend before the message.

        Returns:
            the UUID message and the given payload concatenated.
        """
        encoded_uuid, _ = ElvaMessage.ID.encode(uuid.encode())
        return encoded_uuid + message

    async def _send(
        self,
        message: bytes,
        uuid: str,
        origin_ws: Websocket | None = None,
    ) -> None:
        """
        Forward a message to local or remote connections depending on the message's origin.

        Arguments:
            message: the message to forward.
            uuid: the uuid of the Y document the message belongs to.
            origin_ws: the websocket connection from which the message came.
        """
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
        self,
        message: str,
        uuid: UUID,
        origin_ws: Websocket | None,
        origin_name: str,
    ):
        """
        Send a message over the remote connection.

        Arguments:
            message: the message to send.
            uuid: the UUID of the Y document the message belongs to.
            origin_ws: the websocket connection from which the message came.
            origin_name: the identifier of the websocket connection the message came from.
        """
        # send message to self.remote
        message = self.create_uuid_message(message, uuid)
        self.log.debug(f"> [{uuid}] sending from {origin_name} to remote: {message}")
        await self.send(message)

    async def _send_to_local(
        self,
        message: str,
        uuid: UUID,
        origin_ws: Websocket | None,
        origin_name: str,
    ):
        """
        Send a message to local connections.

        Arguments:
            message: the message to send.
            uuid: the UUID of the Y document the message belongs to.
            origin_ws: the websocket connection from which the message came.
            origin_name: the identifier of the websocket connection the message came from.
        """
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
        """
        Decode a UUID message.

        Arguments:
            message: the message to decode.

        Returns:
            a tuple of the decoded UUID and the payload attached.
        """
        uuid, length = ElvaMessage.ID.decode(message)
        self.log.debug(f"  uuid extracted: {uuid}")
        return uuid.decode(), message[length:]

    async def serve(self, local: Websocket):
        """
        Handler for new websocket connections.

        Arguments:
            local: new local websocket connection.
        """
        uuid = local.path[1:]
        await self._send_from_local(local, uuid)

    async def _send_from_local(self, local: Websocket, uuid: str):
        """
        Routine listening for incoming messages from local websocket connections.

        Arguments:
            local: local websocket connection.
            uuid: UUID of the Y document to which incoming messages belong.
        """
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

    async def on_exception(self, exc: Exception):
        """
        Hook called on an exception raised during the connection setup.

        Arguments:
            exc: the exception raised from the connection setup.
        """
        match type(exc):
            case wsexc.InvalidStatus:
                if (
                    exc.respone.status_code == 401
                    and self.user is not None
                    and self.password is not None
                    and not self.tried_once
                ):
                    header = basic_authorization_header(self.user, self.password)
                    self.options["additional_headers"] = header
                    self.tried_once = True
                    return

                self.log.error(f"{exc}: {exc.response.body.decode()}")
                raise exc
            case wsexc.InvalidURI:
                self.log.error(exc)
                raise exc


def get_websocket_identifier(websocket: Websocket) -> str:
    """
    Get an identifier of a websocket connection object.

    Arguments:
        websocket: the websocket connection to get an identifier for.

    Returns:
        the identifier of the given websocket connection.
    """
    # use memory address of websocket connection as identifier
    return hex(id(websocket))


def get_uuid_from_local_websocket(websocket: Websocket) -> UUID:
    """
    Get the Y document UUID from the connection path.

    Arguments:
        websocket: the websocket connection from which to extract the Y document UUID.

    Returns:
        the path of the websocket connection, which should be the Y document UUID.
    """
    # get room id (uuid) from websocketpath without the leading "/"
    return websocket.path[1:]


async def main(server: WebsocketMetaProvider, host: str, port: int):
    """
    Main routine of the service app.

    Arguments:
        server: the broker component routing messages between local and remote connections.
        host: the host address to listen on for new connections.
        port: the port to listen on for new connections.
    """
    async with websockets.serve(
        server.serve,
        host,
        port,
        process_request=missing_identifier,
        logger=log,
    ):
        async with anyio.create_task_group() as tg:
            await tg.start(server.start)


@click.command()
@click.pass_context
@click.argument("host", default="localhost")
@click.argument("port", default=8000)
def cli(ctx: click.Context, host: str, port: int):
    """
    Launch a relay to an ELVA websocket server.
    \f

    Arguments:
        ctx: the click context holding the configuration parameter object.
        host: the host address to listen on for new connections.
        port: the port to listen on for new connections.
    """

    gather_context_information(ctx, app="service")

    c = ctx.obj

    # checks
    pr = urlparse(c["server"])
    if pr.hostname == host and pr.port == port:
        raise click.BadArgumentUsage(
            f"remote server address '{c["server"]}' is identical to service address 'ws://{host}:{port}'"
        )

    # logging
    LOGGER_NAME.set(__name__)
    if c["log"] is not None:
        log_handler = logging.FileHandler(c["log"])
    else:
        log_handler = logging.StreamHandler(sys.stdout)
    log_handler.setFormatter(DefaultFormatter())
    log.addHandler(log_handler)
    if c["level"] is None:
        level = logging.INFO
    else:
        level = min(logging.INFO, c["level"])
    log.setLevel(level)

    server = WebsocketMetaProvider(
        c["user"],
        c["password"],
        c["server"],
    )

    for name, param in [("host", host), ("port", port)]:
        if c.get(name) is None:
            c[name] = param

    try:
        anyio.run(main, server, c["host"], c["port"])
    except KeyboardInterrupt:
        pass
    log.info("service stopped")


if __name__ == "__main__":
    cli()
