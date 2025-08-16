"""
[`Textual`](https://textual.textualize.io/) screens for ELVA apps.
"""

from rich.text import Text as RichText
from textual.containers import Grid
from textual.message import Message
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Input, Static

from elva.widgets.awareness import AwarenessView
from elva.widgets.config import ConfigView


class Dashboard(Screen):
    def compose(self):
        yield ConfigView()
        yield AwarenessView()

    def key_escape(self):
        self.dismiss()


class InputScreen(ModalScreen):
    def compose(self):
        yield Input()

    def on_input_submitted(self, event: Message):
        self.dismiss(event.value)

    def key_escape(self, event):
        self.dismiss()


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
