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
from elva.protocol import YMessage
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
        print(path, type(path))
        if path is not None:
            print(identifier)
            print(path / identifier)
            self.path = path / identifier
        else:
            self.path = None
        print(self.path, type(self.path))

        self.clients = list()

        if persistent:
            self.ydoc = Doc()
            if path is not None:
                self.store = SQLiteStore(self.ydoc, self.path)

    def callback(self, event):
        if event.update != b"\x00\x00":
            message, _ = YMessage.SYNC_UPDATE.encode(event.update)
            broadcast(self.clients, message)

    async def run(self):
        if self.persistent and self.path is not None:
            self.ydoc.observe(self.callback)
            await self._task_group.start(self.store.start)

    async def cleanup(self):
        async with anyio.create_task_group() as tg:
            tg.start_soon(self.close_all)
            if self.persistent and self.path is not None:
                tg.start_soon(self.store.stop)

    async def close_all(self):
        for client in self.clients:
            await client.close()
        self.log.debug("all clients closed")

    def add(self, client):
        self.clients.append(client)
        self.log.debug(f"added {client} to room ID {self.identifier}")

    def remove(self, client):
        self.clients.remove(client)
        self.log.debug(f"removed {client} from room ID {self.identifier}")

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

    def broadcast(self, data, client):
        # copy current state of clients and remove calling client
        clients = self.clients[:]
        clients.remove(client)

        # broadcast to all other clients
        # TODO: set raise_exceptions=True and catch with ExceptionGroup
        broadcast(clients, data)
        self.log.debug(f"broadcasted {data} from {client} to {clients}")

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
            # message, _ = YMessage.SYNC_UPDATE.encode(update)
            # self.broadcast(message, client)

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
            self.log.info(f"server started on {self.host}:{self.port}")
            await anyio.sleep_forever()

    async def handle(self, websocket):
        identifier = websocket.path[1:]  # remove leading '/'

        if identifier in self.rooms.keys():
            room = self.rooms[identifier]
        else:
            room = Room(identifier, persistent=self.persistent, path=self.path)
            self.rooms[identifier] = room
            await self._task_group.start(room.start)

        room.add(websocket)

        try:
            async for data in websocket:
                await room.process(data, websocket)
        except ConnectionClosed:
            self.log.info("connection closed")
        except Exception as exc:
            self.log.error(f"unexpected exception: {exc}")
        finally:
            room.remove(websocket)
            self.log.debug(f" [{identifier}] removed {websocket}")


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
@click.argument("host", default="localhost")
@click.argument("port", default=8000)
@click.option("--persistent", is_flag=True)
@click.option(
    "--path", type=click.Path(path_type=Path, file_okay=False, resolve_path=True)
)
def cli(host, port, persistent, path):
    print(host, port, persistent, path)

    # logging
    log = logging.getLogger(__name__)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(DefaultFormatter())
    log.addHandler(handler)
    log.setLevel(logging.DEBUG)

    anyio.run(main, host, port, persistent, path)


if __name__ == "__main__":
    cli()
