import logging

import anyio
import websockets.exceptions as wsexc
from textual.app import App
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

from elva.auth import basic_authorization_header
from elva.component import LOGGER_NAME
from elva.log import DefaultFormatter
from elva.provider import WebsocketConnection

LOGGER_NAME.set(__name__)
log = logging.getLogger(__name__)
handler = logging.FileHandler("interactive-provider.log")
handler.setFormatter(DefaultFormatter())
log.addHandler(handler)
log.setLevel(logging.DEBUG)


class CredentialScreen(ModalScreen):
    def __init__(self, connection, body):
        super().__init__()
        self.body = Static(body)
        self.connection = connection
        self.username = Input(placeholder="user name", id="username")
        self.password = Input(placeholder="password", password=True, id="password")

    def compose(self):
        yield self.body
        yield self.username
        yield self.password
        yield Button("Confirm", id="confirm")

    def on_button_pressed(self, event):
        header = basic_authorization_header(
            self.username.value,
            self.password.value,
        )
        self.connection.options["additional_headers"] = header
        self.dismiss()


class URIScreen(ModalScreen):
    def __init__(self, connection):
        super().__init__()
        self.connection = connection
        self.old_uri = Static(connection.uri)
        self.uri = Input(placeholder="new URI")

    def compose(self):
        yield self.old_uri
        yield self.uri
        yield Button("Confirm", id="confirm")

    def on_button_pressed(self, event):
        # update here and not in the app.push_screen(callback=...)
        # the options almost always won't be applied fast enough and
        # the connection is retried with the old values again
        self.connection.options["uri"] = self.uri.value
        self.dismiss()


class CredentialApp(App):
    def __init__(self):
        super().__init__()
        self.label = Static()
        uri = "ws://localhost:8000"
        self.connection = WebsocketConnection(
            uri,
            on_exception=self.on_exception,
        )

    async def on_exception(self, exc):
        match type(exc):
            # use dot-syntax to force a value pattern, i.e. a non-capture pattern
            # see https://docs.python.org/3/reference/compound_stmts.html#value-patterns
            case wsexc.InvalidStatus:
                # TODO: run in worker as suggested by the textual docs?
                await self.push_screen(
                    CredentialScreen(self.connection, exc.response.body.decode()),
                    wait_for_dismiss=True,
                )
            case wsexc.InvalidURI:
                # TODO: run in worker as suggested by the textual docs?
                await self.push_screen(
                    URIScreen(self.connection),
                    wait_for_dismiss=True,
                )
            case _:
                raise exc

    def compose(self):
        yield self.label

    async def run_connection(self):
        async with anyio.create_task_group() as tg:
            await tg.start(self.connection.start)

    def on_mount(self):
        self.run_worker(self.run_connection())

    async def on_unmount(self):
        await self.connection.stopped.wait()


if __name__ == "__main__":
    app = CredentialApp()
    app.run()
