from rich.text import Text as RichText
from textual.containers import Grid
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

from elva.auth import basic_authorization_header


class CredentialScreen(ModalScreen):
    def __init__(self, options, body=None, user=None):
        super().__init__(classes="modalscreen", id="credentialscreen")
        self.options = options
        self.body = Static(RichText(body, justify="center"), id="body")

        self.user = Input(placeholder="user", id="user")
        self.user.value = user or ""
        self.password = Input(placeholder="password", password=True, id="password")

    def compose(self):
        with Grid(classes="form"):
            yield self.body
            yield self.user
            yield self.password
            yield Button("Confirm", classes="confirm")

    def update_and_return_credentials(self):
        credentials = (self.user.value, self.password.value)
        header = basic_authorization_header(*credentials)
        self.options["additional_headers"] = header
        self.password.clear()
        self.dismiss(credentials)

    def on_button_pressed(self, event):
        self.update_and_return_credentials()

    def key_enter(self):
        self.update_and_return_credentials()


class ErrorScreen(ModalScreen):
    def __init__(self, exc):
        super().__init__(classes="modalscreen", id="errorscreen")
        self.exc = exc

    def compose(self):
        with Grid(classes="form"):
            yield Static(
                RichText(
                    "The following error occured and the app will close now:",
                    justify="center",
                )
            )
            yield Static(RichText(str(self.exc), justify="center"))
            yield Button("OK", classes="confirm")

    def on_button_pressed(self, event):
        self.dismiss()
