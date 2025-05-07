"""
Module holding provider components.
"""

from inspect import Signature, signature
from typing import Any
from urllib.parse import urljoin

import anyio
from pycrdt import Doc, Subscription, TransactionEvent
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus, InvalidURI

from elva.auth import basic_authorization_header
from elva.component import Component
from elva.protocol import ElvaMessage, YMessage

# TODO: rewrite Yjs provider with single YDoc
# TODO: rewrite ELVA provider with single YDoc
# TODO: write multi-YDoc ELVA provider as metaprovider, i.e. service


class Connection(Component):
    """
    Abstract base class for connection objects.
    """

    _connected = None
    _disconnected = None
    _outgoing = None
    _incoming = None

    @property
    def connected(self) -> anyio.Event:
        """
        Event signaling being connected.
        """
        if self._connected is None:
            self._connected = anyio.Event()
        return self._connected

    @property
    def disconnected(self) -> anyio.Event:
        """
        Event signaling being disconnected.
        """
        if self._disconnected is None:
            self._disconnected = anyio.Event()
        return self._disconnected

    @property
    def outgoing(self) -> Any:
        """
        Outgoing stream.
        """
        if self._outgoing is None:
            raise RuntimeError("no outgoing stream set")
        return self._outgoing

    @outgoing.setter
    def outgoing(self, stream):
        self._outgoing = stream

    @property
    def incoming(self) -> Any:
        """
        Incoming stream.
        """
        if self._incoming is None:
            raise RuntimeError("no incoming stream set")
        return self._incoming

    @incoming.setter
    def incoming(self, stream):
        self._incoming = stream

    async def send(self, data: Any):
        """
        Wrapper around the [`outgoing.send`][elva.provider.Connection.outgoing] method.

        Arguments:
            data: data to be send via the [`outgoing`][elva.provider.Connection.outgoing] stream.
        """
        if self.connected.is_set():
            try:
                self.log.debug(f"sending {data}")
                await self.outgoing.send(data)
            except Exception as exc:
                self.log.info(f"cancelled sending {data}")
                self.log.debug(f"cancelled due to exception: {exc}")

    async def recv(self):
        """
        Wrapper around the [`incoming`][elva.provider.Connection.incoming] stream.
        """
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

    async def on_recv(self, data: Any):
        """
        Hook executed on received `data` from [`incoming`][elva.provider.Connection.incoming].

        This is defined as a no-op and intended to be defined in the inheriting subclass.

        Arguments:
            data: data received from [`incoming`][elva.provider.Connection.incoming].
        """
        ...


class WebsocketConnection(Connection):
    """
    Websocket connection handling component.
    """

    signature: Signature
    """Object holding the positional and keyword arguments for [`connect`][websockets.asyncio.client.connect]."""

    options: dict
    """Mapping of arguments to the signature of [`connect`][websockets.asyncio.client.connect]."""

    basic_authorization_header: dict
    """Mapping of `Authorization` HTTP request header to encoded `Basic Authentication` information."""

    tried_credentials: bool
    """Flag whether given credentials have already been tried."""

    def __init__(
        self,
        uri: str,
        user: None | str = None,
        password: None | str = None,
        *args: tuple[Any],
        **kwargs: dict[Any],
    ):
        """
        Arguments:
            uri: websocket address to connect to.
            user: username to be sent in the `Basic Authentication` HTTP request header.
            password: password to be sent in the `Basic Authentication` HTTP request header.
            *args: positional arguments passed to [`connect`][websockets.asyncio.client.connect].
            **kwargs: keyword arguments passed to [`connect`][websockets.asyncio.client.connect].
        """
        self.uri = uri
        self._websocket = None

        # construct a dictionary of args and kwargs
        self.signature = signature(connect).bind(uri, *args, **kwargs)
        self.options = self.signature.arguments
        self.options["logger"] = self.log

        # keep credentials separate to only send them if necessary
        if user:
            self.basic_authorization_header = basic_authorization_header(
                user, password or ""
            )
        else:
            self.basic_authorization_header = None

        self.tried_credentials = False

    async def run(self):
        """
        Hook connecting and listening for incoming data.

        - It retries on HTTP response status other than `101` automatically.
        - It sends given credentials only after a failed connection attempt.
        - It gives the opportunity to update the connection arguments with credentials via the
          [`on_exception`][elva.provider.WebsocketConnection.on_exception] hook, if previously
          given information result in a failed connection.
        """
        # catch exceptions due to HTTP status codes other than 101, 3xx, 5xx
        while True:
            try:
                # accepts only 101 and 3xx HTTP status codes,
                # retries only on 5xx by default
                async for self._websocket in connect(
                    *self.signature.args, **self.signature.kwargs
                ):
                    try:
                        self.log.info(f"connection to {self.uri} opened")

                        self.incoming = self._websocket
                        self.outgoing = self._websocket
                        self.connected.set()
                        if self.disconnected.is_set():
                            self._disconnected = None
                            self.log.debug("unset 'disconnected' event flag")
                        self.log.debug("set 'connected' event flag and streams")

                        self._task_group.start_soon(self.on_connect)
                        await self.recv()
                    # we only expect a normal or abnormal connection closing
                    except ConnectionClosed:
                        pass
                    # catch everything else and log it
                    # TODO: remove it? helpful for devs only?
                    except Exception as exc:
                        self.log.exception(
                            f"unexpected websocket client exception: {exc}"
                        )

                    self.log.info(f"connection to {self.uri} closed")
                    self._connected = None
                    self.disconnected.set()
                    self.log.debug("set 'disconnected' event flag")
                    self._outgoing = None
                    self._incoming = None
                    self.log.debug("unset 'connected' event flag and streams")
            # expect only errors occur due to malformed URI or HTTP status code
            # considered invalid
            except (InvalidStatus, InvalidURI) as exc:
                if (
                    self.basic_authorization_header is not None
                    and not self.tried_credentials
                    and isinstance(exc, InvalidStatus)
                    and exc.response.status_code == 401
                ):
                    headers = dict(additional_headers=self.basic_authorization_header)
                    self.options.update(headers)
                    self.tried_credentials = True
                else:
                    try:
                        options = await self.on_exception(exc)
                        if options:
                            if options.get("additional_headers") is not None:
                                self.tried_credentials = False
                            self.options.update(options)
                    except Exception as exc:
                        self.log.error(f"abort due to raised exception {exc}")
                        break

        # when reached this point, something clearly went wrong,
        # so we need to stop the connection
        await self.stop()

    async def cleanup(self):
        """
        Hook closing the websocket connection gracefully if cancelled.
        """
        if self._websocket is not None:
            self.log.debug("closing connection")
            await self._websocket.close()

    async def on_connect(self):
        """
        Hook method run on connection.

        This is defined as a no-op and supposed to be implemented in the inheriting subclass.
        """
        ...

    async def on_exception(self, exc: InvalidURI | InvalidStatus):
        """
        Hook method run on otherwise unhandled invalid URI or invalid HTTP response status.

        This method defaults to re-raise `exc`, is supposed to be implemented in the inheriting subclass and intended to be integrated in a user interface.

        Arguments:
            exc: exception raised by [`connect`][websockets.asyncio.client.connect].
        """
        raise exc


class WebsocketProvider(WebsocketConnection):
    """
    Handler for Y messages sent and received over a websocket connection.

    This component follows the [Yjs protocol spec](https://github.com/yjs/y-protocols/blob/master/PROTOCOL.md).
    """

    ydoc: Doc
    """Instance of the synchronized Y Document."""

    subscription: Subscription
    """Object holding subscription information to changes in [`ydoc`][elva.provider.WebsocketProvider.ydoc]."""

    def __init__(
        self,
        ydoc: Doc,
        identifier: str,
        server: str,
        *args: tuple[Any],
        **kwargs: dict[Any],
    ):
        """
        Arguments:
            ydoc: instance if the synchronized Y Document.
            identifier: identifier of the synchronized Y Document.
            server: address of the Y Document synchronizing websocket server.
            *args: positional arguments passed to [`WebsocketConnection`][elva.provider.WebsocketConnection].
            **kwargs: keyword arguments passed to [`WebsocketConnection`][elva.provider.WebsocketConnection].
        """
        self.ydoc = ydoc
        uri = urljoin(server, identifier)
        super().__init__(uri, *args, **kwargs)

    async def run(self):
        """
        Hook observing changes and handling connection.
        """
        self.subscription = self.ydoc.observe(self.callback)
        await super().run()

    async def cleanup(self):
        """
        Hook cancelling the subscription to changes in [`ydoc`][elva.provider.WebsocketProvider.ydoc].
        """
        self.ydoc.unobserve(self.subscription)

    def callback(self, event: TransactionEvent):
        """
        Hook called on changes in [`ydoc`][elva.provider.WebsocketProvider.ydoc].

        When called, the `event` data are encoded as Y update message and sent over the established websocket connection.

        Arguments:
            event: object holding event information.
        """
        if event.update != b"\x00\x00":
            message, _ = YMessage.SYNC_UPDATE.encode(event.update)
            self.log.debug("callback with non-empty update triggered")
            self._task_group.start_soon(self.send, message)

    async def on_connect(self):
        """
        Hook initializing cross synchronization.

        When called, it sends a Y sync step 1 message and a Y sync step 2 message with respect to the null state, effectively doing a pro-active cross synchronization.
        """
        # init sync
        state = self.ydoc.get_state()
        step1, _ = YMessage.SYNC_STEP1.encode(state)
        await self.send(step1)

        # proactive cross sync
        update = self.ydoc.get_update(b"\x00")
        step2, _ = YMessage.SYNC_STEP2.encode(update)
        await self.send(step2)

    async def on_recv(self, data: bytes):
        """
        Hook called on received `data` over the websocket connection.

        When called, `data` is assumed to be a [`YMessage`][elva.protocol.YMessage] and tried to be decoded.
        On successful decoding, the payload is dispatched to the appropriate method.

        Arguments:
            data: message received from the synchronizing server.
        """
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

    async def on_sync_step1(self, state: bytes):
        """
        Dispatch method called on received Y sync step 1 message.

        It answers the message with a Y sync step 2 message according to the [Yjs protocol spec](https://github.com/yjs/y-protocols/blob/master/PROTOCOL.md).

        Arguments:
            state: payload included in the incoming Y sync step 1 message.
        """
        update = self.ydoc.get_update(state)
        step2, _ = YMessage.SYNC_STEP2.encode(update)
        await self.send(step2)

    async def on_sync_update(self, update: bytes):
        """
        Dispatch method called on received Y sync update message.

        The `update` gets applied to the internal Y Document instance.

        Arguments:
            update: payload included in the incoming Y sync update message.
        """
        if update != b"\x00\x00":
            self.ydoc.apply_update(update)

    # TODO: add awareness functionality
    async def on_awareness(self, state: bytes):
        """
        Dispatch method called on received Y awareness message.

        Currently, this is defined as a no-op.

        Arguments:
            state: payload included in the incoming Y awareness message.
        """
        ...


class ElvaWebsocketProvider(WebsocketConnection):
    """
    Handler for Y messages sent and received over a websocket connection.

    This component follows the ELVA protocol.
    """

    ydoc: Doc
    """Instance of the synchronized Y Document."""

    identifier: str
    """Identifier of the synchronized Y Document."""

    uuid: bytes
    """As `ElvaMessage.ID` message encoded [`identifier`][elva.provider.ElvaWebsocketProvider.identifier]."""

    subscription: Subscription
    """Object holding subscription information to changes in [`ydoc`][elva.provider.ElvaWebsocketProvider.ydoc]."""

    def __init__(
        self,
        ydoc: Doc,
        identifier: str,
        server: str,
        *args: tuple[Any],
        **kwargs: dict[Any],
    ):
        """
        Arguments:
            ydoc: instance if the synchronized Y Document.
            identifier: identifier of the synchronized Y Document.
            server: address of the Y Document synchronizing websocket server.
            *args: positional arguments passed to [`WebsocketConnection`][elva.provider.WebsocketConnection].
            **kwargs: keyword arguments passed to [`WebsocketConnection`][elva.provider.WebsocketConnection].
        """
        self.ydoc = ydoc
        self.identifier = identifier
        self.uuid, _ = ElvaMessage.ID.encode(self.identifier.encode())
        super().__init__(server, *args, **kwargs)

    async def run(self):
        """
        Hook observing changes and handling connection.
        """
        self.subscription = self.ydoc.observe(self.callback)
        await super().run()

    async def cleanup(self):
        """
        Hook cancelling the subscription to changes in [`ydoc`][elva.provider.ElvaWebsocketProvider.ydoc].
        """
        self.ydoc.unobserve(self.subscription)

    async def send(self, data: bytes):
        """
        Send `data` with [`uuid`][elva.provider.ElvaWebsocketProvider.uuid] prepended.

        Arguments:
            data: data to be send over the websocket connection.
        """
        message = self.uuid + data
        await super().send(message)

    def callback(self, event: TransactionEvent):
        """
        Hook called on changes in [`ydoc`][elva.provider.ElvaWebsocketProvider.ydoc].

        When called, the `event` data are encoded as Y update message and sent over the established websocket connection.

        Arguments:
            event: object holding event information.
        """
        if event != b"\x00\x00":
            message, _ = ElvaMessage.SYNC_UPDATE.encode(event.update)
            self.log.debug("callback with non-empty update triggered")
            self._task_group.start_soon(self.send, message)

    async def on_connect(self):
        """
        Hook initializing cross synchronization.

        When called, it sends a Y sync step 1 message and a Y sync step 2 message with respect to the null state, effectively doing a pro-active cross synchronization.
        """
        state = self.ydoc.get_state()
        step1, _ = ElvaMessage.SYNC_STEP1.encode(state)
        await self.send(step1)

        # proactive cross sync
        update = self.ydoc.get_update(b"\x00")
        step2, _ = ElvaMessage.SYNC_STEP2.encode(update)
        await self.send(step2)

    async def on_recv(self, data: bytes):
        """
        Hook called on received `data` over the websocket connection.

        When called, `data` is assumed to be an [`ElvaMessage`][elva.protocol.ElvaMessage] and tried to be decoded.
        On successful decoding, the payload is dispatched to the appropriate method.

        Arguments:
            data: message received from the synchronizing server.
        """
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

    async def on_sync_step1(self, state: bytes):
        """
        Hook called on received Y sync step 1 message.

        It answers the message with a Y sync step 2 message according to the ELVA protocol.

        Arguments:
            state: payload included in the incoming Y sync step 1 message.
        """
        update = self.ydoc.get_update(state)
        step2, _ = ElvaMessage.SYNC_STEP2.encode(update)
        await self.send(step2)

    async def on_sync_update(self, update: bytes):
        """
        Hook called on received Y sync update message.

        The `update` gets applied to the internal Y Document instance.

        Arguments:
            update: payload included in the incoming Y sync update message.
        """
        if update != b"\x00\x00":
            self.ydoc.apply_update(update)

    # TODO: add awareness functionality
    async def on_awareness(self, state: bytes):
        """
        Hook called on received Y awareness message.

        Currently, this is defined as a no-op.

        Arguments:
            state: payload included in the incoming Y awareness message.
        """
        ...
