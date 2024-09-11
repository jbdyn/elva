from http import HTTPStatus
from pathlib import Path

import anyio
from pycrdt import Doc
from websockets import ConnectionClosed, broadcast, serve

from elva.component import Component
from elva.protocol import ElvaMessage, YMessage
from elva.store import SQLiteStore


class RequestProcesser:
    def __init__(self, *funcs):
        self.funcs = funcs

    def process_request(self, path, request):
        for func in self.funcs:
            out = func(path, request)
            if out is not None:
                return out


class Room(Component):
    def __init__(
        self,
        identifier: str,
        persistent: bool = False,
        path: None | Path = None,
    ):
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
        if self.persistent and self.path is not None:
            await self._task_group.start(self.store.start)

    async def cleanup(self):
        async with anyio.create_task_group() as tg:
            # close all clients
            for client in self.clients:
                tg.start_soon(client.close)

        self.log.debug("all clients closed")

    def add(self, client):
        nclients = len(self.clients)
        self.clients.add(client)
        if nclients < len(self.clients):
            self.log.debug(f"added {client} to room '{self.identifier}'")

    def remove(self, client):
        self.clients.remove(client)
        self.log.debug(f"removed {client} from room '{self.identifier}'")

    def broadcast(self, data, client):
        # copy current state of clients and remove calling client
        clients = self.clients.copy()
        clients.remove(client)

        if clients:
            # broadcast to all other clients
            # TODO: set raise_exceptions=True and catch with ExceptionGroup
            broadcast(clients, data)
            self.log.debug(f"broadcasted {data} from {client} to {clients}")

    async def process(self, data, client):
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

    async def process_sync_step1(self, state, client):
        # answer with sync step 2
        update = self.ydoc.get_update(state)
        message, _ = YMessage.SYNC_STEP2.encode(update)
        await client.send(message)

        # reactive cross sync
        state = self.ydoc.get_state()
        message, _ = YMessage.SYNC_STEP1.encode(state)
        await client.send(message)

    async def process_sync_update(self, update, client):
        if update != b"\x00\x00":
            self.ydoc.apply_update(update)

            # reencode sync update message and selectively broadcast
            # to all other clients
            message, _ = YMessage.SYNC_UPDATE.encode(update)
            self.broadcast(message, client)

    async def process_awareness(self, state, client):
        self.log.debug(f"got AWARENESS message {state} from {client}, do nothing")


class ElvaRoom(Room):
    def __init__(self, identifier, persistent, path):
        super().__init__(identifier, persistent=persistent, path=path)
        self.uuid, _ = ElvaMessage.ID.encode(self.identifier.encode())

    def broadcast(self, data, client):
        super().broadcast(self.uuid + data, client)

    async def process(self, data, client):
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

    async def process_sync_step1(self, state, client):
        # answer with sync step 2
        update = self.ydoc.get_update(state)
        message, _ = ElvaMessage.SYNC_STEP2.encode(update)
        await client.send(self.uuid + message)

        # reactive cross sync
        state = self.ydoc.get_state()
        message, _ = ElvaMessage.SYNC_STEP1.encode(state)
        await client.send(self.uuid + message)

    async def process_sync_update(self, update, client):
        if update != b"\x00\x00":
            self.ydoc.apply_update(update)

            # reencode sync update message and selectively broadcast
            # to all other clients
            message, _ = ElvaMessage.SYNC_UPDATE.encode(update)
            self.broadcast(message, client)


class WebsocketServer(Component):
    def __init__(
        self,
        host: str,
        port: int,
        persistent: bool = False,
        path: None | Path = None,
        process_request: None = None,
    ):
        self.host = host
        self.port = port
        self.persistent = persistent
        self.path = path

        if process_request is None:
            self.process_request = self.check_path
        else:
            self.process_request = RequestProcesser(
                self.check_path, process_request
            ).process_request

        self.rooms = dict()

    async def run(self):
        async with serve(
            self.handle,
            self.host,
            self.port,
            process_request=self.process_request,
        ):
            # startup info
            self.log.info(f"server started on {self.host}:{self.port}")

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

    def check_path(self, path, request):
        if path[1:] == "":
            return HTTPStatus.FORBIDDEN, {}, b""

    async def get_room(self, identifier):
        try:
            room = self.rooms[identifier]
        except KeyError:
            room = Room(identifier, persistent=self.persistent, path=self.path)
            self.rooms[identifier] = room
            await self._task_group.start(room.start)

        return room

    async def handle(self, websocket):
        # use the connection path as identifier with leading `/` removed
        identifier = websocket.path[1:]
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
    def check_path(self, path, request):
        if path[1:] != "":
            return HTTPStatus.FORBIDDEN, {}, b""

    async def get_room(self, identifier):
        try:
            room = self.rooms[identifier]
        except KeyError:
            room = ElvaRoom(identifier, persistent=self.persistent, path=self.path)
            self.rooms[identifier] = room
            await self._task_group.start(room.start)

        return room

    async def handle(self, websocket):
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
