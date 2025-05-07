"""
[`Textual`](https://textual.textualize.io/) screens for ELVA apps.
"""

from typing import Any

from rich.text import Text as RichText
from textual.containers import Grid
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

from elva.auth import basic_authorization_header


class CredentialScreen(ModalScreen):
    """
    Modal screen providing a form for credential input.
    """

    options: dict
    """Mapping of options for the connection provider."""

    body: Static
    """Instance of the static widget displaying an informational message."""

    user: Input
    """Instance of the input widget for the user name."""

    password: Input
    """Instance of the input widget for the password."""

    def __init__(
        self, options: dict[str, Any], body: None | str = None, user: None | str = None
    ):
        """
        Arguments:
            options: mapping of options for the connection provider.
            body: informational message displayed above the credential form.
            user: user name.
        """
        super().__init__(classes="modalscreen", id="credentialscreen")
        self.options = options
        self.body = Static(RichText(body, justify="center"), id="body")

        self.user = Input(placeholder="user", id="user")
        self.user.value = user or ""
        self.password = Input(placeholder="password", password=True, id="password")

    def compose(self):
        """
        Hook arranging child widgets.
        """
        with Grid(classes="form"):
            yield self.body
            yield self.user
            yield self.password
            yield Button("Confirm", classes="confirm")

    def update_and_return_credentials(self):
        """
        Save input credentials and return them after closing the screen.

        This method saves the credentials encoded in a basic authorization header in the [`options`][elva.widgets.screens.CredentialScreen.options] attribute for usage in the connection provider.
        """
        credentials = (self.user.value, self.password.value)
        header = basic_authorization_header(*credentials)
        self.options["additional_headers"] = header
        self.password.clear()
        self.dismiss(credentials)

    def on_button_pressed(self, event: Message):
        """
        Hook called on a button pressed event.

        The credentials get updated and the screen closed.

        Arguments:
            event: message object holding information about the button pressed event.
        """
        self.update_and_return_credentials()

    def key_enter(self):
        """
        Hook called on an enter pressed event.

        The credentials get updated and the screen closed.
        """
        self.update_and_return_credentials()


class ErrorScreen(ModalScreen):
    """
    Modal screen displaying an exception message.
    """

    exc: str
    """The exception message to display."""

    def __init__(self, exc: str):
        """
        Arguments:
            exc: the exception message to display.
        """
        super().__init__(classes="modalscreen", id="errorscreen")
        self.exc = exc

    def compose(self):
        """
        Hook arranging child widgets.
        """
        with Grid(classes="form"):
            yield Static(
                RichText(
                    "The following error occured and the app will close now:",
                    justify="center",
                )
            )
            yield Static(RichText(str(self.exc), justify="center"))
            yield Button("OK", classes="confirm")

    def on_button_pressed(self, event: Message):
        """
        Hook called on a button pressed event.

        It closes the screen.

        Arguments:
            event: the message object holding information about the button pressed event.
        """
        self.dismiss(self.exc)
