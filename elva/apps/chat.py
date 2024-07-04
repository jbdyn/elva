import logging
import re
import uuid

import anyio
import click
import emoji
from pycrdt import Array, Doc, Map, Text
from rich.markdown import Markdown as RichMarkdown
from textual.app import App
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Rule, Static, TabbedContent

import elva.log
from elva.apps.editor import YTextArea, YTextAreaParser
from elva.parser import ArrayEventParser, MapEventParser
from elva.provider import ElvaProvider

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

WHITESPACE_ONLY = re.compile(r"^\s*$")


class MessageView(Widget):
    def __init__(self, author, text, **kwargs):
        super().__init__(**kwargs)
        self.text = text
        self.author_field = Static(author, classes="field author")

        content = emoji.emojize(str(text))
        self.text_field = Static(RichMarkdown(content), classes="field content")

    def on_mount(self):
        if not str(self.text):
            self.display = False
        self.text.observe(self.text_callback)

    def compose(self):
        yield self.author_field
        yield self.text_field

    def text_callback(self, event):
        text = str(event.target)
        if re.match(WHITESPACE_ONLY, text) is None:
            self.display = True
            self.text_field.update(RichMarkdown(emoji.emojize(text)))
        else:
            self.display = False


class MessageList(VerticalScroll):
    def __init__(self, messages, **kwargs):
        super().__init__(**kwargs)
        self.messages = messages

    def mount_message_view(self, message, message_id=None):
        author = message["author"]
        text = message["text"]
        if message_id is None:
            message_id = "id" + message["id"]
        return MessageView(author, text, classes="message", id=message_id)


class History(MessageList):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

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
        for message_view in self.widget.children[range_offset:range_offset + range_length]:
            log.debug("deleting message view in history")
            message_view.remove()


class Future(MessageList):
    def __init__(self, messages, username, client_id, show_self=False, **kwargs):
        super().__init__(messages, **kwargs)
        self.username = username
        self.client_id = client_id
        self.show_self = show_self

    def compose(self):
        for message_id, message in self.messages.items():
            if not self.show_self and message["author"] == self.username:
                continue
            else:
                yield self.mount_message_view(message, message_id="id" + message_id)


class FutureParser(MapEventParser):
    def __init__(self, future, widget, username, client_id, show_self):
        self.future = future
        self.widget = widget
        self.username = username
        self.client_id = client_id
        self.show_self = show_self

    def future_callback(self, event):
        log.debug("future callback triggered")
        self._task_group.start_soon(self.parse, event)

    async def run(self):
        self.future.observe(self.future_callback)
        await super().run()

    async def on_add(self, key, new_value):
        if not self.show_self and new_value["author"] == self.username:
            return

        message_view = self.widget.mount_message_view(new_value, message_id="id" + key)
        log.debug("mounting message view in future")
        self.widget.mount(message_view)

    async def on_delete(self, key, old_value):
        message = self.widget.query_one("#id" + key)
        log.debug("deleting message view in future")
        message.remove()


class MessagePreview(Static):
    def __init__(self, ytext, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ytext = ytext

    async def on_show(self):
        self.update(RichMarkdown(emoji.emojize(str(self.ytext))))


def get_chat_provider(Provider: ElvaProvider = ElvaProvider):

    class ChatProvider(Provider):
        def __init__(self, ydocs, uri, future, client_id):
            super().__init__(ydocs, uri)
            self.future = future
            self.client_id = client_id

        async def cleanup(self):
            self.future.pop(self.client_id)

    return ChatProvider


class Chat(Widget):
    BINDINGS = [
        ("ctrl+s", "send", "Send currently composed message")
    ]

    def __init__(self, username, uri, Provider: ElvaProvider=ElvaProvider, show_self=True):
        super().__init__()
        self.username = username

        # structure
        ydoc = Doc()
        ydoc["history"] = self.history = Array()
        ydoc["future"] = self.future = Map()
        self.message, message_id = self.get_message("")
        self.client_id = self.get_new_id()
        self.future[self.client_id] = self.message

        # widgets
        self.history_widget = History(self.history, id="history")
        self.future_widget = Future(self.future, username, self.client_id, show_self=show_self, id="future")
        self.message_widget = YTextArea(self.message["text"], id="editor")
        self.message_widget.language = "markdown"
        self.markdown_widget = MessagePreview(self.message["text"])

        # components
        self.history_parser = HistoryParser(self.history, self.history_widget)
        self.future_parser = FutureParser(self.future, self.future_widget, username, self.client_id, show_self)
        self.message_parser = YTextAreaParser(self.message["text"], self.message_widget)
        ChatProvider = get_chat_provider(Provider)
        self.provider = ChatProvider({'test.chat': ydoc}, uri, self.future, self.client_id)
        self.components = [
            self.history_parser,
            self.future_parser,
            self.message_parser,
            self.provider,
        ]

    def get_new_id(self):
        return str(uuid.uuid4())

    def get_message(self, text, message_id=None):
        if message_id is None:
            message_id = self.get_new_id()
        return Map({
            "text": Text(text),
            "author": self.username,
            "id": message_id,
        }), message_id

    async def run_components(self):
        async with anyio.create_task_group() as self.tg:
            for comp in self.components:
                await self.tg.start(comp.start)

    async def on_mount(self):
        self.run_worker(self.run_components())
        async with anyio.create_task_group() as tg:
            for comp in self.components:
                tg.start_soon(comp.started.wait)

    async def on_unmount(self):
        async with anyio.create_task_group() as tg:
            for comp in self.components:
                tg.start_soon(comp.stopped.wait)

    def compose(self):
        yield self.history_widget
        yield Rule()
        yield self.future_widget
        with TabbedContent("Message", "Preview", id="tabview"):
            yield self.message_widget
            with VerticalScroll():
                yield self.markdown_widget

    async def on_key(self, event):
        if event.is_printable or event.key in ["tab", "enter"]:
            self.message_widget.post_message(event)
            self.message_widget.focus()

    async def action_send(self):
        text = str(self.message["text"])
        if re.match(WHITESPACE_ONLY, text) is None:
            message, _ = self.get_message(text, message_id=self.message["id"])
            self.history.append(message)

            self.message["text"].clear()
            self.message["id"] = self.get_new_id()


class UI(App):
    CSS_PATH = "chat.tcss"

    def __init__(self, username, uri, Provider: ElvaProvider=ElvaProvider, show_self=True):
        super().__init__()
        self.chat = Chat(username, uri, Provider, show_self)

    def compose(self):
        yield self.chat


@click.command()
@click.option(
    "--show-self", "-s", "show_self",
    help="show your own writing as a future message",
    is_flag=True,
    default=False,
    show_default=True
)
@click.pass_context
def cli(ctx, show_self: bool):
    """chat app"""
    
    uri = ctx.obj['uri']
    name = ctx.obj['name']
    provider = ctx.obj['provider']

    app = UI(name, uri, provider, show_self)
    app.run()


if __name__ == "__main__":
    cli()
