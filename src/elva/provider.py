"""
Module holding provider components.
"""

from inspect import Signature, signature
from typing import Any
from urllib.parse import urljoin

from pycrdt import Doc, Subscription, TransactionEvent
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus, InvalidURI

from elva.auth import basic_authorization_header
from elva.component import Component, create_component_state
from elva.protocol import YMessage

WebsocketProviderState = create_component_state(
    "WebsocketProviderState", ("CONNECTED",)
)


class WebsocketProvider(Component):
    """
    Handler for Y messages sent and received over a websocket connection.

    This component follows the [Yjs protocol spec](https://github.com/yjs/y-protocols/blob/master/PROTOCOL.md).
    """

    ydoc: Doc
    """Instance of the synchronized Y Document."""

    options: dict
    """Mapping of arguments to the signature of [`connect`][websockets.asyncio.client.connect]."""

    basic_authorization_header: dict
    """Mapping of `Authorization` HTTP request header to encoded `Basic Authentication` information."""

    tried_credentials: bool
    """Flag whether given credentials have already been tried."""

    _subscription: Subscription
    """Object holding subscription information to changes in [`ydoc`][elva.provider.WebsocketProvider.ydoc]."""

    _signature: Signature
    """Object holding the positional and keyword arguments for [`connect`][websockets.asyncio.client.connect]."""

    def __init__(
        self,
        ydoc: Doc,
        identifier: str,
        server: str,
        user: None | str = None,
        password: None | str = None,
        *args: tuple[Any],
        **kwargs: dict[Any],
    ):
        """
        Arguments:
            ydoc: instance if the synchronized Y Document.
            identifier: identifier of the synchronized Y Document.
            server: address of the Y Document synchronizing websocket server.
            user: username to be sent in the `Basic Authentication` HTTP request header.
            password: password to be sent in the `Basic Authentication` HTTP request header.
            *args: positional arguments passed to [`connect`][websockets.asyncio.client.connect].
            **kwargs: keyword arguments passed to [`connect`][websockets.asyncio.client.connect].
        """
        self.ydoc = ydoc
        uri = urljoin(server, identifier)
        self.uri = uri

        # construct a dictionary of args and kwargs
        self._signature = signature(connect).bind(uri, *args, **kwargs)
        self.options = self._signature.arguments
        self.options["logger"] = self.log

        # keep credentials separate to only send them if necessary
        if user:
            self.basic_authorization_header = basic_authorization_header(
                user, password or ""
            )
        else:
            self.basic_authorization_header = None

        self.tried_credentials = False

    @property
    def states(self) -> WebsocketProviderState:
        """
        The states the websocket provider can have.
        """
        return WebsocketProviderState

    async def before(self):
        """
        Hook subscribing to changes in the Y Document.
        """
        self._subscription = self.ydoc.observe(self.on_transaction_event)

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
                async for self._connection in connect(
                    *self._signature.args, **self._signature.kwargs
                ):
                    try:
                        self.log.info(f"opened connection to {self.uri}")
                        self._change_state(self.states.NONE, self.states.CONNECTED)

                        self._task_group.start_soon(self.on_connect)
                        await self.recv()
                    # we only expect a normal or abnormal connection closing
                    except ConnectionClosed:
                        pass

                    self.log.info(f"closed connection to {self.uri}")

                    # remove `CONNECTED` state
                    self._change_state(self.states.CONNECTED, self.states.NONE)
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
                    options = await self.on_exception(exc)
                    if options:
                        if options.get("additional_headers") is not None:
                            self.tried_credentials = False
                        self.options.update(options)

    async def cleanup(self):
        """
        Hook cancelling the subscription to changes in [`ydoc`][elva.provider.WebsocketProvider.ydoc] and
        closing the websocket connection gracefully if cancelled.
        """
        if hasattr(self, "_subscription"):
            self.ydoc.unobserve(self._subscription)

        if hasattr(self, "_connection"):
            self.log.debug("closing connection")
            await self._connection.close()
            del self._connection

    async def send(self, data: Any):
        """
        Wrapper around the [`outgoing.send`][elva.provider.Connection.outgoing] method.

        Arguments:
            data: data to be send via the [`outgoing`][elva.provider.Connection.outgoing] stream.
        """
        if self.states.CONNECTED in self.state:
            await self._connection.send(data)
            self.log.debug(f"sent data {data}")

    async def recv(self):
        """
        Wrapper around the [`incoming`][elva.provider.Connection.incoming] stream.
        """
        self.log.info("listening for incoming data")
        async for data in self._connection:
            self.log.debug(f"received data {data}")
            await self.on_recv(data)

    def on_transaction_event(self, event: TransactionEvent):
        """
        Hook called on changes in [`ydoc`][elva.provider.WebsocketProvider.ydoc].

        When called, the `event` data are encoded as Y update message and sent over the established websocket connection.

        Arguments:
            event: object holding event information.
        """
        if event.update != b"\x00\x00":
            message, _ = YMessage.SYNC_UPDATE.encode(event.update)
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

    async def on_exception(self, exc: InvalidURI | InvalidStatus) -> None | dict:
        """
        Hook method run on otherwise unhandled invalid URI or invalid HTTP response status.

        This method defaults to re-raise `exc`, is supposed to be implemented in the inheriting subclass and intended to be integrated in a user interface.

        Arguments:
            exc: exception raised by [`connect`][websockets.asyncio.client.connect].

        Returns:
            `None` or a dictionary with additional options for the next connection try.
        """
        raise exc
