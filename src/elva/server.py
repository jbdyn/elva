"""
Websocket server classes.
"""

from http import HTTPStatus
from pathlib import Path
from typing import Callable

import anyio
from pycrdt import Doc
from websockets import (
    ConnectionClosed,
    broadcast,
    serve,
)
from websockets.asyncio.client import ClientConnection
from websockets.asyncio.server import ServerConnection
from websockets.http11 import Request

from elva.component import Component
from elva.protocol import ElvaMessage, YMessage
from elva.store import SQLiteStore


class RequestProcessor:
    """
    Collector class of HTTP request processing functions.
    """

    def __init__(self, *funcs: tuple[Callable]):
        """
        Arguments:
            funcs: HTTP request processing functions.
        """
        self.funcs = funcs

    def process_request(
        self, websocket: ServerConnection, request: Request
    ) -> None | tuple[HTTPStatus, dict[str, str], None | bytes]:
        """
        Process a HTTP request for given functions.

        This function is designed to be given to [`serve`][websockets.asyncio.server.serve].

        Arguments:
            websocket: connection object.
            request: HTTP request header object.

        Returns:
            Abort information like in [`abort_basic_auth`][elva.auth.abort_basic_auth] on first occurence, else `None`.
        """
        for func in self.funcs:
            out = func(websocket, request)
            if out is not None:
                return out


class Room(Component):
    """
    Connection handler for one Y Document following the Yjs protocol.
    """

    identifier: str
    """Identifier of the synchronized Y Document."""

    persistent: bool
    """Flag whether to store received Y Document updates."""

    path: None | Path
    """Path where to save a Y Document on disk."""

    clients: set[ClientConnection]
    """Set of active connections."""

    ydoc: Doc
    """Y Document instance holding received updates."""

    store: SQLiteStore
    """component responsible for writing received Y updates to disk."""

    def __init__(
        self,
        identifier: str,
        persistent: bool = False,
        path: None | Path = None,
    ):
        """
        If `persistent = False` and `path = None`, messages will be broadcasted only.
        Nothing is saved.

        If `persistent = True` and `path = None`, a Y Document will be present in this room, saving all incoming Y updates in there. This happens only in volatile memory.

        If `persistent = True` and `path = Path(to/some/directory)`, a Y Document will be present and its contents will be saved to disk under the given directory.
        The name of the corresponding file is derived from [`identifier`][elva.server.Room.identifier].

        Arguments:
            identifier: identifier for the used Y Document.
            persistent: flag whether to store received Y Document updates.
            path: path where to save a Y Document on disk.
        """
        self.identifier = identifier
        self.persistent = persistent

        if path is not None:
            self.path = path / identifier
        else:
            self.path = None

        self.clients = set()

        if persistent:
            self.ydoc = Doc()
            if path is not None:
                self.store = SQLiteStore(self.ydoc, identifier, self.path)

    async def before(self):
        """
        Hook runnig before the [`started`][elva.component.Component.started] signal is set.

        Used to start the Y Document store.
        """
        if self.persistent and self.path is not None:
            await self._task_group.start(self.store.start)

    async def cleanup(self):
        """
        Hook running after the component got cancelled and before its [`stopped`][elva.component.Component.stopped] signal is set.

        Used to close all client connections gracefully.
        The store is closed automatically and calls its cleanup method separately.
        """
        async with anyio.create_task_group() as tg:
            # close all clients
            for client in self.clients:
                tg.start_soon(client.close)

        self.log.debug("all clients closed")

    def add(self, client: ClientConnection):
        """
        Add a client connection.

        Arguments:
            client: connection to add the list of connections.
        """
        nclients = len(self.clients)
        self.clients.add(client)
        if nclients < len(self.clients):
            self.log.debug(f"added {client} to room '{self.identifier}'")

    def remove(self, client: ClientConnection):
        """
        Remove a client connection.

        Arguments:
            client: connection to remove from the list of connections.
        """
        self.clients.remove(client)
        self.log.debug(f"removed {client} from room '{self.identifier}'")

    def broadcast(self, data: bytes, client: ClientConnection):
        """
        Broadcast `data` to all clients except `client`.

        Arguments:
            data: data to send.
            client: connection from which `data` came and thus to exclude from broadcasting.
        """
        # copy current state of clients and remove calling client
        clients = self.clients.copy()
        clients.remove(client)

        if clients:
            # broadcast to all other clients
            # TODO: set raise_exceptions=True and catch with ExceptionGroup
            broadcast(clients, data)
            self.log.debug(f"broadcasted {data} from {client} to {clients}")

    async def process(self, data: bytes, client: ClientConnection):
        """
        Process incoming messages from `client`.

        If `persistent = False`, just call [`broadcast(data, client)`][elva.server.Room.broadcast].

        If `persistent = True`, `data` is assumed to be a Y message and tried to be decomposed.
        On successful decomposition, actions are taken according to the [Yjs protocol spec](https://github.com/yjs/y-protocols/blob/master/PROTOCOL.md).

        Arguments:
            data: data received from `client`.
            client: connection from which `data` was received.
        """
        if self.persistent:
            # properly dispatch message
            try:
                message_type, payload, _ = YMessage.infer_and_decode(data)
            except ValueError:
                return

            match message_type:
                case YMessage.SYNC_STEP1:
                    await self.process_sync_step1(payload, client)
                case YMessage.SYNC_STEP2 | YMessage.SYNC_UPDATE:
                    await self.process_sync_update(payload, client)
                case YMessage.AWARENESS:
                    await self.process_awareness(payload, client)
        else:
            # simply forward incoming messages to all other clients
            self.broadcast(data, client)

    async def process_sync_step1(self, state: bytes, client: ClientConnection):
        """
        Process a sync step 1 payload `state` from `client`.

        Answer it with a sync step 2.
        Also, start a reactive cross-sync by answering with a sync step 1 additionally.

        Arguments:
            state: payload of the received sync step 1 message from `client`.
            client: connection from which the sync step 1 message came.
        """
        # answer with sync step 2
        update = self.ydoc.get_update(state)
        message, _ = YMessage.SYNC_STEP2.encode(update)
        await client.send(message)

        # reactive cross sync
        state = self.ydoc.get_state()
        message, _ = YMessage.SYNC_STEP1.encode(state)
        await client.send(message)

    async def process_sync_update(self, update: bytes, client: ClientConnection):
        """
        Process a sync update message payload `update` from `client`.

        Apply the update to the internal [`ydoc`][elva.server.Room.ydoc] instance and broadcast the same update to all other clients than `client`.

        Arguments:
            update: payload of the received sync update message from `client`.
            client: connection from which the sync update message came.
        """
        if update != b"\x00\x00":
            self.ydoc.apply_update(update)

            # reencode sync update message and selectively broadcast
            # to all other clients
            message, _ = YMessage.SYNC_UPDATE.encode(update)
            self.broadcast(message, client)

    async def process_awareness(self, state: bytes, client: ClientConnection):
        """
        Process an awareness message payload `state` from `client`.

        Currently, this is implemented as a no-op.
        """
        self.log.debug(f"got AWARENESS message {state} from {client}, do nothing")


class ElvaRoom(Room):
    """
    Connection handler for one Y Document following the ELVA protocol.
    """

    uuid: bytes
    """As [`ElvaMessage`][elva.protocol.ElvaMessage] encoded [`identifier`][elva.server.Room.identifier]."""

    def __init__(self, identifier: str, persistent: bool, path: None | Path):
        """
        If `persistent = False` and `path = None`, messages will be broadcasted only.
        Nothing is saved.

        If `persistent = True` and `path = None`, a Y Document will be present in this room, saving all incoming Y updates in there. This happens only in volatile memory.

        If `persistent = True` and `path = Path(to/some/directory)`, a Y Document will be present and its contents will be saved to disk under the given directory.
        The name of the corresponding file is derived from [`identifier`][elva.server.Room.identifier].

        Arguments:
            identifier: identifier for the used Y Document.
            persistent: flag whether to store received Y Document updates.
            path: path where to save a Y Document on disk.
        """

        super().__init__(identifier, persistent=persistent, path=path)
        self.uuid, _ = ElvaMessage.ID.encode(self.identifier.encode())

    def broadcast(self, data: bytes, client: ClientConnection):
        """
        Broadcast `data` to all clients except `client`.

        Arguments:
            data: data to send.
            client: connection from which `data` came and thus to exclude from broadcasting.
        """
        super().broadcast(self.uuid + data, client)

    async def process(self, data: bytes, client: ClientConnection):
        """
        Process incoming messages from `client`.

        If `persistent = False`, just call [`broadcast(data, client)`][elva.server.ElvaRoom.broadcast].

        If `persistent = True`, `data` is assumed to be a Y message and tried to be decomposed.
        On successful decomposition, actions are taken according to the [Yjs protocol spec](https://github.com/yjs/y-protocols/blob/master/PROTOCOL.md).

        Arguments:
            data: data received from `client`.
            client: connection from which `data` was received.
        """
        if self.persistent:
            # properly dispatch message
            try:
                message_type, payload, _ = ElvaMessage.infer_and_decode(data)
            except ValueError:
                return

            match message_type:
                case ElvaMessage.SYNC_STEP1:
                    await self.process_sync_step1(payload, client)
                case ElvaMessage.SYNC_STEP2 | ElvaMessage.SYNC_UPDATE:
                    await self.process_sync_update(payload, client)
                case ElvaMessage.AWARENESS:
                    await self.process_awareness(payload, client)
        else:
            # simply forward incoming messages to all other clients
            self.broadcast(data, client)

    async def process_sync_step1(self, state: bytes, client: ClientConnection):
        """
        Process a sync step 1 payload `state` from `client`.

        Answer it with a sync step 2.
        Also, start a reactive cross-sync by answering with a sync step 1 additionally.

        Arguments:
            state: payload of the received sync step 1 message from `client`.
            client: connection from which the sync step 1 message came.
        """
        # answer with sync step 2
        update = self.ydoc.get_update(state)
        message, _ = ElvaMessage.SYNC_STEP2.encode(update)
        await client.send(self.uuid + message)

        # reactive cross sync
        state = self.ydoc.get_state()
        message, _ = ElvaMessage.SYNC_STEP1.encode(state)
        await client.send(self.uuid + message)

    async def process_sync_update(self, update: bytes, client: ClientConnection):
        """
        Process a sync update message payload `update` from `client`.

        Apply the update to the internal `self.ydoc` instance and broadcast the same update to all other clients than `client`.

        Arguments:
            update: payload of the received sync update message from `client`.
            client: connection from which the sync update message came.
        """
        if update != b"\x00\x00":
            self.ydoc.apply_update(update)

            # reencode sync update message and selectively broadcast
            # to all other clients
            message, _ = ElvaMessage.SYNC_UPDATE.encode(update)
            self.broadcast(message, client)


class WebsocketServer(Component):
    """
    Serving component using [`Room`][elva.server.Room] as internal connection handler.
    """

    host: str
    """hostname or IP address to be published at."""

    port: int
    """port to listen on."""

    persistent: bool
    """flag whether to save Y Document updates persistently."""

    path: None | Path
    """path where to store Y Document contents on disk."""

    process_request: Callable
    """callable checking the HTTP request headers on new connections."""

    rooms: dict[str, Room]
    """mapping of connection handlers to their corresponding identifiers."""

    def __init__(
        self,
        host: str,
        port: int,
        persistent: bool = False,
        path: None | Path = None,
        process_request: None | Callable = None,
    ):
        """
        Arguments:
            host: hostname or IP address to be published at.
            port: port to listen on.
            persistent: flag whether to save Y Document updates persistently.
            path: path where to store Y Document contents on disk.
            process_request: callable checking the HTTP request headers on new connections.
        """
        self.host = host
        self.port = port
        self.persistent = persistent
        self.path = path

        if process_request is None:
            self.process_request = self.check_path
        else:
            self.process_request = RequestProcessor(
                self.check_path, process_request
            ).process_request

        self.rooms = dict()

    async def run(self):
        """
        Hook handling incoming connections and messages.
        """
        async with serve(
            self.handle,
            self.host,
            self.port,
            process_request=self.process_request,
            logger=self.log,
        ):
            if self.persistent:
                message_template = "storing content in {}"
                if self.path is None:
                    location = "volatile memory"
                else:
                    location = self.path
                self.log.info(message_template.format(location))
            else:
                self.log.info("broadcast only and no content will be stored")

            # keep the server active indefinitely
            await anyio.sleep_forever()

    def check_path(self, websocket: ServerConnection, request: Request):
        """
        Check if a request path is valid.

        This function is a request processing callable and automatically passed to the inner [`serve`][websockets.asyncio.server.serve] function.

        Arguments:
            websocket: connection object.
            request: HTTP request header object.
        """
        if request.path[1:] == "":
            return HTTPStatus.FORBIDDEN, {}, b""

    async def get_room(self, identifier: str) -> Room:
        """
        Get or create a [`Room`][elva.server.Room] via its corresponding `identifier`.

        Arguments:
            identifier: string identifiying the underlying Y Document.

        Returns:
            room to the given `identifier`.
        """
        try:
            room = self.rooms[identifier]
        except KeyError:
            room = Room(identifier, persistent=self.persistent, path=self.path)
            self.rooms[identifier] = room
            await self._task_group.start(room.start)

        return room

    async def handle(self, websocket: ClientConnection):
        """
        Handle a `websocket` connection.

        Upon connection, a room is provided, to which the data are given for further processing.

        This methods is passed to [`serve`][websockets.asyncio.server.serve] internally.

        Arguments:
            websocket: connection from data are being received.
        """
        # use the connection path as identifier with leading `/` removed
        identifier = websocket.request.path[1:]
        room = await self.get_room(identifier)

        room.add(websocket)

        try:
            async for data in websocket:
                await room.process(data, websocket)
        except ConnectionClosed:
            self.log.info("connection closed")
        except Exception as exc:
            self.log.error(f"unexpected exception: {exc}")
            await websocket.close()
            self.log.error(f"closed {websocket}")
        finally:
            room.remove(websocket)
            self.log.debug(f" [{identifier}] removed {websocket}")


class ElvaWebsocketServer(WebsocketServer):
    """
    Serving component using [`ElvaRoom`][elva.server.ElvaRoom] as internal connection handler.
    """

    def check_path(self, websocket: ServerConnection, request: Request):
        """
        Check if a request path is valid.

        This function is a request processing callable and automatically passed to the inner [`serve`][websockets.asyncio.server.serve] function.

        Arguments:
            websocket: connection object.
            request: HTTP request header object.
        """
        if request.path[1:] != "":
            return HTTPStatus.FORBIDDEN, {}, b""

    async def get_room(self, identifier: str) -> ElvaRoom:
        """
        Get or create an [`ElvaRoom`][elva.server.ElvaRoom] via its corresponding `identifier`.

        Arguments:
            identifier: string identifiying the underlying Y Document.

        Returns:
            room to the given `identifier`.
        """
        try:
            room = self.rooms[identifier]
        except KeyError:
            room = ElvaRoom(identifier, persistent=self.persistent, path=self.path)
            self.rooms[identifier] = room
            await self._task_group.start(room.start)

        return room

    async def handle(self, websocket: ClientConnection):
        """
        Handle a `websocket` connection.

        Upon connection, an room is provided, to which the data are given for further processing.

        This method is passed to [`serve`][websockets.asyncio.server.serve] internally.

        Arguments:
            websocket: connection from data are being received.
        """
        try:
            async for data in websocket:
                # use the identifier from the received message
                identifier, length = ElvaMessage.ID.decode(data)
                identifier = identifier.decode()

                # get the room
                room = await self.get_room(identifier)

                # room.clients is a set, so no duplicates
                room.add(websocket)

                # cut off the identifier part and process the rest
                message = data[length:]
                await room.process(message, websocket)
        except ConnectionClosed:
            self.log.info(f"{websocket} remotely closed")
        except Exception as exc:
            self.log.error(f"unexpected exception: {exc}")
            await websocket.close()
            self.log.error(f"closed {websocket}")
        finally:
            for room in self.rooms.values():
                try:
                    room.remove(websocket)
                    self.log.debug(f" [{room.identifier}] removed {websocket}")
                except KeyError:
                    pass
