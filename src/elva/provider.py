from inspect import signature
from urllib.parse import urljoin

import anyio
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus, InvalidURI

from elva.component import Component
from elva.protocol import ElvaMessage, YMessage

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
    def __init__(self, uri, *args, **kwargs):
        self.uri = uri
        self._websocket = None

        # construct a dictionary of args and kwargs
        sig = signature(connect)
        self._arguments = sig.bind(uri, *args, **kwargs)
        self.options = self._arguments.arguments
        self.options["logger"] = self.log

    async def run(self):
        # catch exceptions due to HTTP status codes other than 101, 3xx, 5xx
        while True:
            try:
                # accepts only 101 and 3xx HTTP status codes,
                # retries only on 5xx by default
                async for self._websocket in connect(
                    *self._arguments.args, **self._arguments.kwargs
                ):
                    try:
                        self.log.info(f"connection to {self.uri} opened")

                        self.incoming = self._websocket
                        self.outgoing = self._websocket
                        self.connected.set()
                        self.log.debug("set 'connected' event flag and streams")

                        self._task_group.start_soon(self.on_connect)
                        await self.recv()
                    # we only expect a normal or abnormal connection closing
                    except ConnectionClosed:
                        self.log.info(f"connection to {self.uri} closed")
                        self._connected = None
                        self._outgoing = None
                        self._incoming = None
                        self.log.debug("unset 'connected' event flag and streams")
                        continue
                    # catch everything else and log it
                    # TODO: remove it? helpful for devs only?
                    except Exception as exc:
                        self.log.exception(
                            f"unexpected websocket client exception: {exc}"
                        )
            # expect only errors occur due to malformed URI or HTTP status code
            # considered invalid
            except (InvalidStatus, InvalidURI) as exc:
                try:
                    options = await self.on_exception(exc)
                    if options:
                        self.options.update(options)
                except Exception as exc:
                    self.log.error(f"abort due to raised exception {exc}")
                    break

        # when reached this point, something clearly went wrong,
        # so we need to stop the connection
        await self.stop()

    async def cleanup(self):
        if self._websocket is not None:
            self.log.debug("closing connection")
            await self._websocket.close()

    async def on_connect(self): ...

    async def on_exception(self, exc):
        raise exc


class WebsocketProvider(WebsocketConnection):
    def __init__(self, ydoc, identifier, server):
        self.ydoc = ydoc
        uri = urljoin(server, identifier)
        super().__init__(uri)

    async def run(self):
        self.ydoc.observe(self.callback)
        await super().run()

    def callback(self, event):
        if event.update != b"\x00\x00":
            message, _ = YMessage.SYNC_UPDATE.encode(event.update)
            self.log.debug("callback with non-empty update triggered")
            self._task_group.start_soon(self.send, message)

    async def on_connect(self):
        # init sync
        state = self.ydoc.get_state()
        step1, _ = YMessage.SYNC_STEP1.encode(state)
        await self.send(step1)

        # proactive cross sync
        update = self.ydoc.get_update(b"\x00")
        step2, _ = YMessage.SYNC_STEP2.encode(update)
        await self.send(step2)

    async def on_recv(self, data):
        try:
            message_type, payload, _ = YMessage.infer_and_decode(data)
        except Exception as exc:
            self.log.debug(f"failed to infer message: {exc}")
            return

        match message_type:
            case YMessage.SYNC_STEP1:
                await self.on_sync_step1(payload)
            case YMessage.SYNC_STEP2 | YMessage.SYNC_UPDATE:
                await self.on_sync_update(payload)
            case YMessage.AWARENESS:
                await self.on_awareness(payload)
            case _:
                self.log.warning(
                    f"message type '{message_type}' does not match any YMessage"
                )

    async def on_sync_step1(self, state):
        update = self.ydoc.get_update(state)
        step2, _ = YMessage.SYNC_STEP2.encode(update)
        await self.send(step2)

    async def on_sync_update(self, update):
        if update != b"\x00\x00":
            self.ydoc.apply_update(update)

    # TODO: add awareness functionality
    async def on_awareness(self, state): ...


class ElvaWebsocketProvider(WebsocketConnection):
    def __init__(self, ydoc, identifier, server):
        self.ydoc = ydoc
        self.identifier = identifier
        self.uuid, _ = ElvaMessage.ID.encode(self.identifier.encode())
        super().__init__(server)

    async def run(self):
        self.ydoc.observe(self.callback)
        await super().run()

    async def send(self, data):
        message = self.uuid + data
        await super().send(message)

    def callback(self, event):
        if event != b"\x00\x00":
            message, _ = ElvaMessage.SYNC_UPDATE.encode(event.update)
            self.log.debug("callback with non-empty update triggered")
            self._task_group.start_soon(self.send, message)

    async def on_connect(self):
        state = self.ydoc.get_state()
        step1, _ = ElvaMessage.SYNC_STEP1.encode(state)
        await self.send(step1)

        # proactive cross sync
        update = self.ydoc.get_update(b"\x00")
        step2, _ = ElvaMessage.SYNC_STEP2.encode(update)
        await self.send(step2)

    async def on_recv(self, data):
        try:
            uuid, length = ElvaMessage.ID.decode(data)
        except ValueError as exc:
            self.log.debug(f"expected ID message: {exc}")
            return

        uuid = uuid.decode()

        if uuid != self.identifier:
            self.log.debug(
                f"received message for ID '{uuid}' instead of '{self.identifier}'"
            )
            return

        data = data[length:]

        try:
            message_type, payload, _ = ElvaMessage.infer_and_decode(data)
        except Exception as exc:
            self.log.debug(f"failed to infer message: {exc}")
            return

        match message_type:
            case ElvaMessage.SYNC_STEP1:
                await self.on_sync_step1(payload)
            case ElvaMessage.SYNC_STEP2 | ElvaMessage.SYNC_UPDATE:
                await self.on_sync_update(payload)
            case ElvaMessage.AWARENESS:
                await self.on_awareness(payload)
            case _:
                self.log.debug(
                    f"message type '{message_type}' does not match any ElvaMessage"
                )

    async def on_sync_step1(self, state):
        update = self.ydoc.get_update(state)
        step2, _ = ElvaMessage.SYNC_STEP2.encode(update)
        await self.send(step2)

    async def on_sync_update(self, update):
        if update != b"\x00\x00":
            self.ydoc.apply_update(update)

    # TODO: add awareness functionality
    async def on_awareness(self, state): ...
