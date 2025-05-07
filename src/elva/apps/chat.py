"""
ELVA chat app.
"""

import logging
import re
import uuid
from pathlib import Path

import anyio
import click
import emoji
import websockets.exceptions as wsexc
from pycrdt import Array, ArrayEvent, Doc, Map, MapEvent, Text, TextEvent
from rich.markdown import Markdown as RichMarkdown
from rich.text import Text as RichText
from textual.app import App
from textual.containers import VerticalScroll
from textual.css.query import NoMatches
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Rule, Static, TabbedContent, TabPane

from elva.auth import basic_authorization_header
from elva.log import LOGGER_NAME, DefaultFormatter
from elva.parser import ArrayEventParser, MapEventParser
from elva.provider import ElvaWebsocketProvider, WebsocketProvider
from elva.store import SQLiteStore
from elva.utils import gather_context_information
from elva.widgets.screens import CredentialScreen, ErrorScreen
from elva.widgets.textarea import YTextArea

log = logging.getLogger(__name__)

WHITESPACE_ONLY = re.compile(r"^\s*$")
"""Regular Expression for whitespace-only messages."""


class MessageView(Widget):
    """
    Widget displaying a single message alongside its metadata.
    """

    def __init__(self, author: str, text: Text, **kwargs: dict):
        """
        Arguments:
            author: the author of the message.
            text: an instance of a Y text data type holding the message content.
            kwargs: keyword arguments passed to [`Widget`][textual.widget.Widget].
        """
        super().__init__(**kwargs)
        self.text = text
        self.author = author

        content = emoji.emojize(str(text))
        self.text_field = Static(RichMarkdown(content), classes="field content")
        self.text_field.border_title = self.author

    def on_mount(self):
        """
        Hook called on mounting the widget.

        This method subscribes to changes in the message text and displays it if there is some content to show.
        """
        if not str(self.text):
            self.display = False
        self.text.observe(self.text_callback)

    def compose(self):
        """
        Hook arranging child widgets.
        """
        yield self.text_field

    def text_callback(self, event: TextEvent):
        """
        Hook called on changes in the message text.

        This method updates the visibility of the view in dependence of the message content.

        Arguments:
            event: object holding information about the changes in the Y text.
        """
        text = str(event.target)
        if re.match(WHITESPACE_ONLY, text) is None:
            self.display = True
            content = emoji.emojize(text)
            self.text_field.update(RichMarkdown(content))
        else:
            self.display = False


class MessageList(VerticalScroll):
    """
    Base container class for [`MessageView`][elva.apps.chat.MessageView] widgets.
    """

    def __init__(self, messages: Array | Map, user: str, **kwargs: dict):
        """
        Arguments:
            messages: Y array or Y map containing message objects.
            user: the current username of the app.
            kwargs: keyword arguments passed to [`VerticalScroll`][textual.containers.VerticalScroll].
        """
        super().__init__(**kwargs)
        self.user = user
        self.messages = messages

    def mount_message_view(
        self, message: Map | dict, message_id: None | str = None
    ) -> MessageView:
        """
        Create a [`MessageView`][elva.apps.chat.MessageView].

        Arguments:
            message: mapping of message attributes.
            message_id: `Textual` DOM tree identifier to assign to the message view.

        Returns:
            a message view to be mounted inside an instance of this class.
        """
        author = f"{message["author_display"]} ({message["author"]})"
        text = message["text"]
        if message_id is None:
            message_id = "id" + message["id"]
        message_view = MessageView(author, text, classes="message", id=message_id)
        if message["author"] == self.user:
            border_title_align = "right"
        else:
            border_title_align = "left"
        message_view.text_field.styles.border_title_align = border_title_align
        return message_view


class History(MessageList):
    """
    List of already sent messages.
    """

    def compose(self):
        """
        Hook arranging child widgets.
        """
        for message in self.messages:
            message_view = self.mount_message_view(message)
            yield message_view


class HistoryParser(ArrayEventParser):
    """
    Parser for changes in the message history.

    This class reflects the state of the Y array with history message in the [`History`][elva.apps.chat.History] message list on changes.
    """

    def __init__(self, history: Array, widget: History):
        """
        Arguments:
            history: Y array containing already sent messages.
        """
        self.history = history
        self.widget = widget

    def history_callback(self, event: ArrayEvent):
        """
        Hook called on a change in the Y array message history.

        This method parses the event and calls the defined action hooks accordingly.

        Arguments:
            event: an object holding information about the change in the Y array.
        """
        log.debug("history callback triggered")
        self._task_group.start_soon(self.parse, event)

    async def run(self):
        """
        Hook called after the component sets the [`started`][elva.component.Component.started] signal.

        This method subscribes to changes in the Y array message history.
        """
        self.history.observe(self.history_callback)
        await super().run()

    async def on_insert(self, range_offset: int, insert_value: str):
        """
        Hook called on an insert action in a Y array change event.

        This methods creates a new message view and mounts it to the message history.

        Arguments:
            range_offset: the start index of the insert.
            insert_value: the inserted content.
        """
        for message in insert_value:
            message_view = self.widget.mount_message_view(message)
            log.debug("mounting message view in history")
            self.widget.mount(message_view)

    async def on_delete(self, range_offset: int, range_length: str):
        """
        Hook called on a delete action in a Y array change event.

        This method removes the all message views in the given index range.

        Arguments:
            range_offset: the start index of the deletion.
            range_length: the number of subsequent indices.
        """
        for message_view in self.widget.children[
            range_offset : range_offset + range_length
        ]:
            log.debug("deleting message view in history")
            message_view.remove()


class Future(MessageList):
    """
    List of currently composed messages.
    """

    def __init__(
        self, messages: Map, user: str, show_self: bool = False, **kwargs: dict
    ):
        """
        Arguments:
            messages: mapping of message identifiers to their corresponding message object.
            user: the current username of the app.
            show_self: flag whether to show the own currently composed message.
            kwargs: keyword arguments passed to [`MessageList`][elva.apps.chat.MessageList].
        """
        super().__init__(messages, user, **kwargs)
        self.show_self = show_self

    def compose(self):
        """
        Hook arranging child widgets.
        """
        for message_id, message in self.messages.items():
            if not self.show_self and message["author"] == self.user:
                continue
            else:
                message_view = self.mount_message_view(
                    message, message_id="id" + message_id
                )
                yield message_view


class FutureParser(MapEventParser):
    """
    Parser for changes in currently composed messages.

    This class reflects the state of the Y map with currently composed messaged in the [`Future`][elva.apps.chat.Future] message list on changes.
    """

    def __init__(self, future: Map, widget: Future, user: str, show_self: bool):
        """
        Arguments:
            future: Y map mapping message identifiers to their corresponding message objects.
            widget: the message list widget displaying the currently composed messages.
            user: the current username.
            show_self: flag whether to show the own currently composed message.
        """
        self.future = future
        self.widget = widget
        self.user = user
        self.show_self = show_self

    def future_callback(self, event: MapEvent):
        """
        Hook called on changes in the Y map.

        This method parses the event object and calls action hooks accordingly.

        Arguments:
            event: an object holding information about the change in the Y map.
        """
        log.debug("future callback triggered")
        self._task_group.start_soon(self.parse, event)

    async def run(self):
        """
        Hook called after the component set the [`started`][elva.component.Component.started] signal.

        This method subscribes to changes in the mapping of currently composed messages.
        """
        self.future.observe(self.future_callback)
        await super().run()

    async def on_add(self, key: str, new_value: dict):
        """
        Hook called on an add action.

        This methods generates a message view from the added message object and mounts it to the list of currently composed messages.

        Arguments:
            key: the message id that has been added.
            new_value: the message object that has been added.
        """
        if not self.show_self and new_value["author"] == self.user:
            return

        message_view = self.widget.mount_message_view(new_value, message_id="id" + key)
        log.debug("mounting message view in future")
        self.widget.mount(message_view)

    async def on_delete(self, key: str, old_value: dict):
        """
        Hook called on a delete action.

        This methods removes the message view corresponding to the removed message id.

        Arguments:
            key: the message id that has been deleted.
            old_value: the message object that has been deleted.
        """
        try:
            message = self.widget.query_one("#id" + key)
            log.debug("deleting message view in future")
            message.remove()
        except NoMatches:
            pass


class MessagePreview(Static):
    """
    Preview of the rendered markdown content.
    """

    def __init__(self, ytext: Text, *args: tuple, **kwargs: dict):
        """
        Arguments:
            ytext: Y text with the markdown content of the own currently composed message.
            args: positional arguments passed to [`Static`][textual.widgets.Static].
            kwargs: keyword arguments passed to [`Static`][textual.widgets.Static].
        """
        super().__init__(*args, **kwargs)
        self.ytext = ytext

    async def on_show(self):
        """
        Hook called on a show message.
        """
        self.update(RichMarkdown(emoji.emojize(str(self.ytext))))


def get_chat_provider(messages: str) -> WebsocketProvider | ElvaWebsocketProvider:
    """
    Get the chat provider handling the given message type.

    Arguments:
        messages: string naming the used message type.

    Returns:
        the provider component handling Y updates over a network connection.
    """
    match messages:
        case "yjs" | None:
            BaseProvider = WebsocketProvider
        case "elva":
            BaseProvider = ElvaWebsocketProvider

    class ChatProvider(BaseProvider):
        def __init__(self, ydoc, identifier, server, future, session_id):
            super().__init__(ydoc, identifier, server)
            self.future = future
            self.session_id = session_id

        # TODO: hangs randomly, FutureParser maybe?
        # causes "Transaction.__exit__ return exception set"
        async def cleanup(self):
            self.future.pop(self.session_id)

    return ChatProvider


class UI(App):
    """
    User interface.
    """

    CSS_PATH = "chat.tcss"
    """Path to the applied textual CSS file."""

    BINDINGS = [("ctrl+s", "send", "Send currently composed message")]
    """Key bindings for controlling the app."""

    def __init__(
        self,
        user: str,
        name: str,
        password: str,
        server: str,
        identifier: str,
        messages: str,
        file_path: Path,
        show_self: bool = True,
    ):
        """
        Arguments:
            user: the current user name to login with.
            name: the name to display instead of the user name.
            password: the password to login with.
            server: the server address to connect to for synchronization.
            identifier: the identifier of this chat document.
            messages: the message type to use.
            file_path: path to an ELVA SQLite database file holding the content of the chat.
            show_self: flag whether to show the own currently composed message.
        """
        super().__init__()
        self.user = user
        self.display_name = name
        self.password = password

        # structure
        ydoc = Doc()
        ydoc["history"] = self.history = Array()
        ydoc["future"] = self.future = Map()
        self.message, message_id = self.get_message("")
        self.session_id = self.get_new_id()
        self.future[self.session_id] = self.message

        # widgets
        self.history_widget = History(self.history, user, id="history")
        self.history_widget.can_focus = False
        self.future_widget = Future(
            self.future, self.user, show_self=show_self, id="future"
        )
        self.future_widget.can_focus = False
        self.message_widget = YTextArea(
            self.message["text"], id="editor", language="markdown"
        )
        self.markdown_widget = MessagePreview(self.message["text"])

        # components
        self.history_parser = HistoryParser(self.history, self.history_widget)
        self.future_parser = FutureParser(
            self.future,
            self.future_widget,
            self.user,
            show_self,
        )

        self.components = [
            self.history_parser,
            self.future_parser,
        ]

        if server is not None and identifier is not None:
            Provider = get_chat_provider(messages)
            self.provider = Provider(
                ydoc,
                identifier,
                server,
                self.future,
                self.session_id,
            )
            self.provider.on_exception = self.on_exception

            self.credential_screen = CredentialScreen(
                self.provider.options, "", self.user
            )

            self.install_screen(self.credential_screen, name="credential_screen")

            self.tried_auto = False
            self.tried_modal = False

            self.components.append(self.provider)

        if file_path is not None:
            self.store = SQLiteStore(self.ydoc, identifier, file_path)
            self.components.append(self.store)

    def get_new_id(self) -> str:
        """
        Get a new message id.

        Returns:
            a UUID v4 identifier.
        """
        return str(uuid.uuid4())

    def get_message(self, text: str, message_id: None | str = None) -> Map:
        """
        Get a message object.

        Arguments:
            text: the content of the message.
            message_id: the identifier of the message.

        Returns:
            a Y map containing a mapping of message attributes.
        """
        if message_id is None:
            message_id = self.get_new_id()
        return Map(
            {
                "text": Text(text),
                "author_display": self.display_name or self.user,
                # we assume that self.user is unique in the room, ensured by the server
                "author": self.user,
                "id": message_id,
            }
        ), message_id

    async def on_exception(self, exc: Exception):
        """
        Hook called on an exception raised within the provider component.

        This method handles connection errors due to wrong credentials or other issues.

        Arguments:
            exc: exception raised within the provider component.
        """
        match type(exc):
            case wsexc.InvalidStatus:
                if exc.response.status_code == 401:
                    if (
                        self.user is not None
                        and self.password is not None
                        and not self.tried_auto
                        and not self.tried_modal
                    ):
                        header = basic_authorization_header(self.user, self.password)

                        self.provider.options["additional_headers"] = header
                        self.tried_auto = True
                    else:
                        body = exc.response.body.decode()
                        self.credential_screen.body.update(
                            RichText(body, justify="center")
                        )
                        self.credential_screen.user.clear()
                        self.credential_screen.user.insert_text_at_cursor(
                            self.user or ""
                        )

                        await self.push_screen(
                            self.credential_screen,
                            self.update_credentials,
                            wait_for_dismiss=True,
                        )

                        self.tried_modal = True
                else:
                    await self.push_screen(
                        ErrorScreen(exc),
                        self.quit_on_error,
                        wait_for_dismiss=True,
                    )
                    raise exc
            case wsexc.InvalidURI:
                await self.push_screen(
                    ErrorScreen(exc),
                    self.quit_on_error,
                    wait_for_dismiss=True,
                )
                raise exc

    def update_credentials(self, credentials: tuple[str, str]):
        """
        Hook called on new credentials.

        Arguments:
            credentials: a tuple of user name and password.
        """
        old_user = self.user
        self.user, self.password = credentials

        if old_user != self.user:
            self.future_widget.query_one(
                "#id" + self.session_id
            ).author = f"{self.display_name or self.user} ({self.user})"

    async def quit_on_error(self, exc: Exception):
        """
        Hook called on closing an [`ErrorScreen`][elva.widgets.screens.ErrorScreen].

        This method exits the app.

        Arguments:
            exc: the exception caught by the ErrorScreen.
        """
        self.exit()

    async def run_components(self):
        """
        Run all components the chat app needs.
        """
        async with anyio.create_task_group() as self.tg:
            for comp in self.components:
                await self.tg.start(comp.start)

    async def on_mount(self):
        """
        Hook called on mounting the app.

        This methods waits for all components to set their [`started`][elva.component.Component.started] signal.
        """
        self.run_worker(self.run_components())
        self.message_widget.focus()

        async with anyio.create_task_group() as tg:
            for comp in self.components:
                tg.start_soon(comp.started.wait)

    async def on_unmount(self):
        """
        Hook called when unmounting, i.e. closing, the app.

        This methods waits for all components to set their [`stopped`][elva.component.Component.stopped] signal.
        """
        async with anyio.create_task_group():
            # TODO: take a closer look on the dependencies between components
            #       and stop accordingly
            for comp in reversed(self.components):
                await comp.stopped.wait()

    def compose(self):
        """
        Hook arranging child widgets.
        """
        yield self.history_widget
        yield Rule(line_style="heavy")
        yield self.future_widget
        with TabbedContent(id="tabview"):
            with TabPane("Message", id="tab-message"):
                yield self.message_widget
            with TabPane("Preview", id="tab-preview"):
                with VerticalScroll():
                    yield self.markdown_widget

    async def action_send(self):
        """
        Hook called on an invoked send action.

        This method transfers the message from the future to the history.
        """
        text = str(self.message["text"])
        if re.match(WHITESPACE_ONLY, text) is None:
            message, _ = self.get_message(text, message_id=self.message["id"])
            self.history.append(message)

            self.message["text"].clear()
            self.message["id"] = self.get_new_id()

    def on_tabbed_content_tab_activated(self, event: Message):
        """
        Hook called on a tab activated message from a tabbed content widget.

        Arguments:
            event: object holding information about the tab activated message.
        """
        if event.pane.id == "tab-message":
            self.message_widget.focus()


@click.command
@click.pass_context
@click.option(
    "--show-self",
    "-s",
    "show_self",
    help="Show your own writing in the preview.",
    is_flag=True,
    default=False,
    show_default=True,
)
@click.argument(
    "file",
    required=False,
    type=click.Path(path_type=Path, dir_okay=False),
)
def cli(ctx, show_self: bool, file: None | Path):
    """
    Send messages with real-time preview.
    \f

    Arguments:
        show_self: flag whether to show the own currently composed message.
        file: path to an ELVA SQLite database file.
    """

    gather_context_information(ctx, file, app="chat")

    c = ctx.obj

    # logging
    LOGGER_NAME.set(__name__)
    log_path = c["log"]
    level = c["level"]

    if level is not None and log_path is not None:
        handler = logging.FileHandler(log_path)
        handler.setFormatter(DefaultFormatter())
        log.addHandler(handler)
        log.setLevel(level)

    for name, param in [("file", file), ("show_self", show_self)]:
        if c.get(name) is None:
            c[name] = param

    # init and run app
    app = UI(
        c["user"],
        c["name"],
        c["password"],
        c["server"],
        c["identifier"],
        c["messages"],
        c["file"],
        c["show_self"],
    )
    app.run()


if __name__ == "__main__":
    cli()
