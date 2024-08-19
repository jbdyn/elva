import logging
import signal
import sys
from pathlib import Path

import anyio
import click
from pycrdt import Doc
from websockets import ConnectionClosed, broadcast, serve

from elva.component import Component
from elva.log import DefaultFormatter
from elva.protocol import ElvaMessage, YMessage
from elva.store import SQLiteStore


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
            print(identifier)
            print(path / identifier)
            self.path = path / identifier
        else:
            self.path = None

        self.clients = set()

        if persistent:
            self.ydoc = Doc()
            if path is not None:
                self.store = SQLiteStore(self.ydoc, self.path)

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
        self.clients.add(client)
        self.log.debug(f"added {client} to room {self.identifier}")

    def remove(self, client):
        self.clients.remove(client)
        self.log.debug(f"removed {client} from room {self.identifier}")

    def broadcast(self, data, client):
        # copy current state of clients and remove calling client
        clients = self.clients.copy()
        clients.remove(client)

        # broadcast to all other clients
        # TODO: set raise_exceptions=True and catch with ExceptionGroup
        broadcast(clients, data)
        self.log.debug(f"broadcasted {data} from {client} to {clients}")

    async def process(self, data, client):
        if self.persistent:
            # properly dispatch message
            message_type, payload, _ = YMessage.infer_and_decode(data)
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

    async def process_sync_step1(self, payload, client):
        # answer with sync step 2
        state = payload
        update = self.ydoc.get_update(state)
        message, _ = YMessage.SYNC_STEP2.encode(update)
        await client.send(message)

        # init inverse sync
        state = self.ydoc.get_state()
        message, _ = YMessage.SYNC_STEP1.encode(state)
        await client.send(message)

    async def process_sync_update(self, payload, client):
        update = payload
        if update != b"\x00\x00":
            self.ydoc.apply_update(update)

            # reencode sync update message and selectively broadcast
            # to all other clients
            message, _ = YMessage.SYNC_UPDATE.encode(update)
            self.broadcast(message, client)

    async def process_awareness(self, payload, client):
        self.log.debug(f"got AWARENESS message {payload} from {client}, do nothing")


class WebsocketServer(Component):
    def __init__(
        self,
        host: str,
        port: int,
        persistent: bool = False,
        path: None | Path = None,
    ):
        self.host = host
        self.port = port
        self.persistent = persistent
        self.path = path

        self.rooms = dict()

    async def run(self):
        async with serve(self.handle, self.host, self.port):
            # startup info
            self.log.info(f"server started on {self.host}:{self.port}")

            if self.persistent:
                message_template = "persistence: storing content in {}"
                if self.path is None:
                    location = "volatile memory"
                else:
                    location = self.path
                self.log.info(message_template.format(location))
            else:
                self.log.info(
                    "persistence: broadcast only and no content will be stored"
                )

            # keep the server active indefinitely
            await anyio.sleep_forever()

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
    async def handle(self, websocket):
        try:
            async for data in websocket:
                # use the identifier from the received message
                identifier, length = ElvaMessage.decode(data)

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
            for room in self.rooms:
                try:
                    room.remove(websocket)
                    self.log.debug(f" [{room.identifier}] removed {websocket}")
                except KeyError:
                    pass


async def main(host, port, persistent, path):
    server = WebsocketServer(host, port, persistent, path)

    async with anyio.create_task_group() as tg:
        await tg.start(server.start)
        with anyio.open_signal_receiver(signal.SIGINT, signal.SIGTERM) as signals:
            async for signum in signals:
                if signum == signal.SIGINT:
                    server.log.info("process received SIGINT")
                else:
                    server.log.info("process received SIGTERM")

                await server.stop()
                break


@click.command()
@click.pass_context
@click.argument("host", default="localhost")
@click.argument("port", default=8000)
@click.option(
    "--persistent",
    # one needs to set this manually here since one cannot use
    # the keyword argument `type=click.Path(...)` as it would collide
    # with `flag_value=""`
    metavar="[DIRECTORY]",
    help=(
        "Hold the received content in a local YDoc in volatile memory "
        "or also save it under DIRECTORY if given."
        "Without this flag, the server simply broadcasts all incoming messages "
        "within the respective room."
    ),
    # explicitely stating that the argument to this option is optional
    # see: https://github.com/pallets/click/pull/1618#issue-649167183
    is_flag=False,
    # used when no argument is given to flag
    flag_value="",
)
def cli(ctx: click.Context, host, port, persistent):
    match persistent:
        # no flag given
        case None:
            path = None
        # flag given, but without a path
        case "":
            path = None
            persistent = True
        # anything else, i.e. a flag given with a path
        case _:
            path = Path(persistent).resolve()
            if path.exists() and not path.is_dir():
                raise click.BadArgumentUsage(
                    f"the given path '{path}' is not a directory", ctx
                )
            path.mkdir(exist_ok=True, parents=True)
            persistent = True

    # logging
    log = logging.getLogger(__name__)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(DefaultFormatter())
    log.addHandler(handler)
    log.setLevel(logging.DEBUG)

    anyio.run(main, host, port, persistent, path)


if __name__ == "__main__":
    cli()
