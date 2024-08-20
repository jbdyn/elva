from dataclasses import dataclass
from functools import partial

import anyio
import websockets
from pycrdt import Doc

from elva.component import Component
from elva.protocol import ElvaMessage, YCodec, YIncrementalDecoder

# TODO: rewrite Yjs provider with single YDoc
# TODO: rewrite ELVA provider with single YDoc
# TODO: write multi-YDoc ELVA provider as metaprovider, i.e. service


class Connection(Component):
    _connected = None
    _outgoing = None
    _incoming = None

    @property
    def connected(self):
        if self._connected is None:
            self._connected = anyio.Event()
        return self._connected

    @property
    def outgoing(self):
        if self._outgoing is None:
            raise RuntimeError("no outgoing stream set")
        return self._outgoing

    @outgoing.setter
    def outgoing(self, stream):
        self._outgoing = stream

    @property
    def incoming(self):
        if self._incoming is None:
            raise RuntimeError("no incoming stream set")
        return self._incoming

    @incoming.setter
    def incoming(self, stream):
        self._incoming = stream

    async def send(self, data):
        if self.connected.is_set():
            try:
                self.log.debug(f"sending {data}")
                await self.outgoing.send(data)
            except Exception as exc:
                self.log.info(f"cancelled sending {data}")
                self.log.debug(f"cancelled due to exception: {exc}")

    async def recv(self):
        self.log.debug("waiting for connection")
        await self.connected.wait()
        try:
            self.log.info("listening")
            async for data in self.incoming:
                self.log.debug(f"received message {data}")
                await self.on_recv(data)
        except Exception as exc:
            self.log.info("cancelled listening for incoming data")
            self.log.debug(f"cancelled due to exception: {exc}")

    async def on_recv(self, data): ...


class WebsocketConnection(Connection):
    def __init__(self, uri):
        self.uri = uri
        self._websocket = None

    async def run(self):
        async for self._websocket in websockets.connect(self.uri):
            try:
                self.log.info(f"connection to {self.uri} opened")

                self.incoming = self._websocket
                self.outgoing = self._websocket
                self.connected.set()
                self.log.debug("set 'connected' event flag and streams")

                self._task_group.start_soon(self.on_connect)
                await self.recv()
            except websockets.ConnectionClosed:
                self.log.info(f"connection to {self.uri} closed")
                self._connected = None
                self._outgoing = None
                self._incoming = None
                self.log.debug("unset 'connected' event flag and streams")
                continue
            except Exception as exc:
                self.log.exception(f"unexpected websocket client exception: {exc}")
                break

    async def cleanup(self):
        if self._websocket is not None:
            self.log.debug("closing connection")
            await self._websocket.close()

    async def on_connect(self): ...


@dataclass
class UUIDMessage:
    uuid: str
    ydoc: Doc
    payload: bytes


class ElvaProvider(WebsocketConnection):
    def __init__(self, ydocs: dict[str, Doc], uri):
        super().__init__(uri)
        self.ydocs = ydocs
        self.ycodec = YCodec()

    def add(self, ydocs):
        self.ydocs.update(ydocs)
        for uuid in ydocs.keys():
            self._task_group.start_soon(self.sync, uuid)

    def remove(self, ydocs):
        self.ydocs.remove(ydocs)

    async def run(self):
        for uuid in self.ydocs.keys():
            self.ydocs[uuid].observe(partial(self.callback, uuid=uuid))
        await super().run()

    async def on_connect(self):
        self.log.info("synchronize all YDocs")
        await self.sync_all()

    async def send_uuid(self, message, uuid):
        self.log.debug("tag message with uuid")
        encoded_uuid, _ = ElvaMessage.ID.encode(uuid.encode())
        message = encoded_uuid + message
        try:
            await self.send(message)
        except Exception:
            pass

    async def on_recv(self, message):
        try:
            uuid, length = ElvaMessage.ID.decode(message)
        except ValueError as exc:
            self.log.debug(f"expected ID message, got {exc}")
            return

        self.log.debug(f"UUID: {uuid}")
        uuid = uuid.decode()

        try:
            ydoc = self.ydocs[uuid]
        except KeyError:
            self.log.debug(f"no YDoc with UUID {uuid} present")
            return

        message = UUIDMessage(uuid, ydoc, message[length:])
        self.log.debug(f"received {message} for {uuid}")
        await self.process(message)

    async def sync_all(self):
        for uuid in self.ydocs.keys():
            self.log.debug(f"syncing UUID {uuid}")
            await self.sync(uuid)

    async def sync(self, uuid):
        ydoc = self.ydocs[uuid]
        state = ydoc.get_state()
        msg, _ = ElvaMessage.SYNC_STEP1.encode(state)
        self.log.debug("sending SYNC_STEP1 message")
        await self.send_uuid(msg, uuid)

    def callback(self, event, uuid):
        try:
            if event.update != b"\x00\x00":
                message, _ = ElvaMessage.SYNC_UPDATE.encode(event.update)
                self.log.debug(f"update message {message} from observer callback")
                self._task_group.start_soon(self.send_uuid, message, uuid)
        except Exception:
            self.log.exception(f"unexpected observer callback error for UUID {uuid}")

    async def process_sync_step1(self, message):
        ydoc = message.ydoc
        state = message.payload
        update = ydoc.get_update(state)
        state = ydoc.get_state()
        encoded_update, _ = self.ycodec.encode(update)
        encoded_state, _ = self.ycodec.encode(state)
        payload = encoded_update + encoded_state
        reply, _ = ElvaMessage.SYNC_CROSS.encode(payload)
        self.log.debug(f"sending cross_sync message {reply}")
        await self.send_uuid(reply, message.uuid)

    async def process_sync_update(self, message):
        ydoc = message.ydoc
        update = message.payload
        if update != b"\x00\x00":
            ydoc.apply_update(update)

    async def process_sync_cross(self, message):
        ydoc = message.ydoc
        dec = YIncrementalDecoder()
        update, _ = dec.decode(message.payload)
        state, _ = dec.decode(message.payload)
        message.payload = update
        await self.process_sync_update(message)

        update = ydoc.get_update(state)
        reply, _ = ElvaMessage.SYNC_STEP2.encode(update)
        await self.send_uuid(reply, message.uuid)

    async def process(self, message):
        try:
            message_type, payload, _ = ElvaMessage.infer_and_decode(message.payload)
        except ValueError as exc:
            self.log.debug(f"expected some kind of ElvaMessage, got {exc}")
            return
        message.payload = payload
        self.log.debug(f"received {message_type} message {payload}")
        match message_type:
            case ElvaMessage.SYNC_STEP1:
                await self.process_sync_step1(message)
            case ElvaMessage.SYNC_CROSS:
                await self.process_sync_cross(message)
            case ElvaMessage.SYNC_STEP2 | ElvaMessage.SYNC_UPDATE:
                await self.process_sync_update(message)
            case _:
                self.log.debug(f"do nothing with {message_type} message {payload}")


class SingleElvaProvider(ElvaProvider):
    def __init__(self, ydocs: dict[str, Doc], uri, without_uuid: bool = False):
        if without_uuid:
            if len(ydocs) != 1:
                raise Exception("dict ydocs has one than entry")
            self.send_uuid = self.send_without_uuid

        super().__init__(ydocs, uri)

    async def send_without_uuid(self, message, uuid=None):
        try:
            await self.send(message)
        except Exception:
            pass


class WebsocketElvaProvider(ElvaProvider):
    def __init__(self, ydocs: dict[str, Doc], uri: str):
        super().__init__(ydocs, uri)

    async def send_uuid(self, message, uuid=None):
        try:
            await self.send(message)
        except Exception:
            pass

    async def on_recv(self, message):
        ydoc = list(self.ydocs.values())[0]
        self.log.debug(f"received message {message}")
        inbound = UUIDMessage(None, ydoc, message)
        await self.process(inbound)

    async def process_sync_step1(self, message):
        ydoc = message.ydoc
        state = message.payload
        update = ydoc.get_update(state)
        reply, _ = ElvaMessage.SYNC_STEP2.encode(update)
        self.log.debug(f"sending sync_step2 message {reply}")
        await self.send_uuid(reply)
