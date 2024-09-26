import logging
import re
import uuid
from pathlib import Path

import anyio
import click
import emoji
import websockets.exceptions as wsexc
from pycrdt import Array, Doc, Map, Text
from rich.markdown import Markdown as RichMarkdown
from rich.text import Text as RichText
from textual.app import App
from textual.containers import VerticalScroll
from textual.css.query import NoMatches
from textual.widget import Widget
from textual.widgets import Rule, Static, TabbedContent, TabPane

from elva.apps.editor import CredentialScreen, ErrorScreen
from elva.auth import basic_authorization_header
from elva.document import YTextArea
from elva.log import LOGGER_NAME, DefaultFormatter
from elva.parser import ArrayEventParser, MapEventParser
from elva.provider import ElvaWebsocketProvider, WebsocketProvider
from elva.store import SQLiteStore
from elva.utils import gather_context_information

log = logging.getLogger(__name__)

WHITESPACE_ONLY = re.compile(r"^\s*$")


class MessageView(Widget):
    def __init__(self, author, text, **kwargs):
        super().__init__(**kwargs)
        self.text = text
        self.author = author

        content = emoji.emojize(str(text))
        self.text_field = Static(RichMarkdown(content), classes="field content")
        self.text_field.border_title = self.author

    def on_mount(self):
        if not str(self.text):
            self.display = False
        self.text.observe(self.text_callback)

    def compose(self):
        yield self.text_field

    def text_callback(self, event):
        text = str(event.target)
        if re.match(WHITESPACE_ONLY, text) is None:
            self.display = True
            content = emoji.emojize(text)
            self.text_field.update(RichMarkdown(content))
        else:
            self.display = False


class MessageList(VerticalScroll):
    def __init__(self, messages, user, **kwargs):
        super().__init__(**kwargs)
        self.user = user
        self.messages = messages

    def mount_message_view(self, message, message_id=None):
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
    def compose(self):
        for message in self.messages:
            message_view = self.mount_message_view(message)
            yield message_view


class HistoryParser(ArrayEventParser):
    def __init__(self, history, widget):
        self.history = history
        self.widget = widget

    def history_callback(self, event):
        log.debug("history callback triggered")
        self._task_group.start_soon(self.parse, event)

    async def run(self):
        self.history.observe(self.history_callback)
        await super().run()

    async def on_insert(self, range_offset, insert_value):
        for message in insert_value:
            message_view = self.widget.mount_message_view(message)
            log.debug("mounting message view in history")
            self.widget.mount(message_view)

    async def on_delete(self, range_offset, range_length):
        for message_view in self.widget.children[
            range_offset : range_offset + range_length
        ]:
            log.debug("deleting message view in history")
            message_view.remove()


class Future(MessageList):
    def __init__(self, messages, user, show_self=False, **kwargs):
        super().__init__(messages, user, **kwargs)
        self.show_self = show_self

    def compose(self):
        for message_id, message in self.messages.items():
            if not self.show_self and message["author"] == self.user:
                continue
            else:
                message_view = self.mount_message_view(
                    message, message_id="id" + message_id
                )
                yield message_view


class FutureParser(MapEventParser):
    def __init__(self, future, widget, user, show_self):
        self.future = future
        self.widget = widget
        self.user = user
        self.show_self = show_self

    def future_callback(self, event):
        log.debug("future callback triggered")
        self._task_group.start_soon(self.parse, event)

    async def run(self):
        self.future.observe(self.future_callback)
        await super().run()

    async def on_add(self, key, new_value):
        if not self.show_self and new_value["author"] == self.user:
            return

        message_view = self.widget.mount_message_view(new_value, message_id="id" + key)
        log.debug("mounting message view in future")
        self.widget.mount(message_view)

    async def on_delete(self, key, old_value):
        try:
            message = self.widget.query_one("#id" + key)
            log.debug("deleting message view in future")
            message.remove()
        except NoMatches:
            pass


class MessagePreview(Static):
    def __init__(self, ytext, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ytext = ytext

    async def on_show(self):
        self.update(RichMarkdown(emoji.emojize(str(self.ytext))))


def get_chat_provider(messages):
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
    CSS_PATH = "chat.tcss"

    BINDINGS = [("ctrl+s", "send", "Send currently composed message")]

    def __init__(
        self,
        user,
        name,
        password,
        server,
        identifier,
        messages,
        file_path,
        show_self=True,
    ):
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

    def get_new_id(self):
        return str(uuid.uuid4())

    def get_message(self, text, message_id=None):
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

    async def on_exception(self, exc):
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

    def update_credentials(self, credentials):
        old_user = self.user
        self.user, self.password = credentials

        if old_user != self.user:
            self.future_widget.query_one(
                "#id" + self.session_id
            ).author = f"{self.display_name or self.user} ({self.user})"

    async def quit_on_error(self, error):
        self.exit()

    async def run_components(self):
        async with anyio.create_task_group() as self.tg:
            for comp in self.components:
                await self.tg.start(comp.start)

    async def on_mount(self):
        self.run_worker(self.run_components())
        self.message_widget.focus()

        async with anyio.create_task_group() as tg:
            for comp in self.components:
                tg.start_soon(comp.started.wait)

    async def on_unmount(self):
        async with anyio.create_task_group():
            # TODO: take a closer look on the dependencies between components
            #       and stop accordingly
            for comp in reversed(self.components):
                await comp.stopped.wait()

    def compose(self):
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
        text = str(self.message["text"])
        if re.match(WHITESPACE_ONLY, text) is None:
            message, _ = self.get_message(text, message_id=self.message["id"])
            self.history.append(message)

            self.message["text"].clear()
            self.message["id"] = self.get_new_id()

    def on_tabbed_content_tab_activated(self, event):
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
    """Send messages with real-time preview."""

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
