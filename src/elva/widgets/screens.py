"""
[`Textual`](https://textual.textualize.io/) screens for ELVA apps.
"""

from textual.message import Message
from textual.screen import ModalScreen, Screen
from textual.widgets import Input, Static

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

    def __init__(self, exc: str, *args, **kwargs):
        """
        Arguments:
            exc: the exception message to display.
        """
        super().__init__(*args, **kwargs)
        self.exc = exc

    def compose(self):
        """
        Hook arranging child widgets.
        """
        yield Static("The following error occured and the app will close now:")
        yield Static(self.exc)
        yield Static("Press any key or click to continue.")

    def on_button_pressed(self, event: Message):
        """
        Hook called on a button pressed event.

        It closes the screen.

        Arguments:
            event: the message object holding information about the button pressed event.
        """
        self.dismiss(self.exc)

    def on_key(self):
        self.dismiss(self.exc)

    def on_mouse_up(self):
        self.dismiss(self.exc)
