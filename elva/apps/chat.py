import uuid
from functools import partial
import sys

import anyio
from pycrdt import Doc, Array, Text, Map, TextEvent, ArrayEvent, MapEvent
from textual.app import App
from textual.widget import Widget
from textual.widgets import Input, Static, ListView, ListItem, Label
from textual.containers import VerticalScroll
from textual.reactive import reactive
import websockets

from elva.provider import ElvaProvider
from elva.apps.editor import YTextArea
from elva.parser import TextEventParser, ArrayEventParser, MapEventParser


class MessageView(Static):
    def __init__(self, author, text, **kwargs):
        super().__init__(**kwargs)
        self.text = text
        self.author_field = Static(author, classes="field author")
        self.text_field = Static(str(text), classes="field content")

    def on_mount(self):
        self.text.observe(self.text_callback)

    def compose(self):
        yield self.author_field
        yield self.text_field

    def text_callback(self, event):
        self.text_field.update(str(event.target))


class MessageList(VerticalScroll, can_focus_children=False):
    def __init__(self, messages, username, **kwargs):
        super().__init__(**kwargs)
        self.messages = messages
        self.username = username

    def mount_message_view(self, message):
        author = message["author"]
        text = message["text"]
        save_id = "id" + message["id"].replace("-", "")
        return MessageView(author, text, id=save_id, classes="message")


class History(MessageList):
    class Parser(ArrayEventParser):
        def __init__(self, history):
            self.history = history

        async def on_insert(self, range_offset, insert_value):
            for message in insert_value:
                message_view = self.history.mount_message_view(message)
                self.history.mount(message_view)

        async def on_delete(self, range_offset, range_length):
            for message_view in self.history.children[range_offset:range_offset + range_length]:
                message_view.remove()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parser = self.Parser(self)

    async def run_parser(self):
        async with anyio.create_task_group() as self.tg:
            await self.tg.start(self.parser.start)

    def on_mount(self):
        self.run_worker(self.run_parser())
        self.messages.observe(self.history_callback)

    def compose(self):
        for message in self.messages:
            message_view = self.mount_message_view(message)
            yield message_view

    def history_callback(self, event):
        self.tg.start_soon(self.parser.parse, event)


class Future(MessageList):
    class Parser(MapEventParser):
        def __init__(self, future, username, show_self):
            self.future = future
            self.username = username
            self.show_self = show_self

        async def on_add(self, key, new_value):
            message_view = self.future.mount_message_view(new_value)
            if not self.show_self and new_value["author"] == self.username:
                return
            else:
                self.future.mount(message_view)

        async def on_delete(self, key, old_value):
            try:
                message = self.future.query_one("#id" + key.replace("-", ""))
                message.remove()
            except:
                pass

    def __init__(self, *args, show_self=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.show_self = show_self
        self.parser = self.Parser(self, self.username, self.show_self)

    async def run_parser(self):
        async with anyio.create_task_group() as self.tg:
            await self.tg.start(self.parser.start)

    def on_mount(self):
        self.run_worker(self.run_parser())
        self.messages.observe(self.future_callback)

    def compose(self):
        for message_id, message in self.messages:
            message_view = self.mount_message_view(message)
            if not self.show_self and author == self.username:
                continue
            else:
                yield message_view

    def future_callback(self, event):
        self.tg.start_soon(self.parser.parse, event)
      

class UI(App):

    CSS_PATH = "chat.tcss"

    BINDINGS = [
        ("ctrl+s", "send", "Send currently composed message")
    ]

    def __init__(self, history, future, username):
        super().__init__()
        self.history = History(history, username, id="history")
        self.future = Future(future, username, id="future")
        self.username = username
        self.message = None

    def compose(self):
        yield self.history
        yield self.future

    async def on_key(self, event):
        if event.is_printable and self.message is None:
            self.message_id = str(uuid.uuid4())
            self.message_text = Text(event.character)
            self.message = Map({
                "text": self.message_text,
                "author": self.username,
                "id": self.message_id,
            })
            self.future.messages[self.message_id] = self.message
            self.message_editor = YTextArea(self.message_text, id="editor")
            self.mount(self.message_editor)
            self.message_editor.focus()

        if event.is_printable:
            self.message_editor.focus()

        if self.message is not None and str(self.message["text"]) == "" and event.key != "ctrl+s":
            self.future.messages.pop(self.message_id)
            self.message_editor.remove()
            self.message = None

    async def action_send(self):
        if self.message is not None:
            # copy message content
            message = self.future.messages.pop(self.message_id)
            message_text = Text(message["text"])
            message["text"] = message_text
            message = Map(message)
            
            self.history.messages.append(message)

            self.message_editor.remove()
            self.message = None


async def main(name):
    # structure
    ydoc = Doc()
    ydoc["history"] = history = Array()
    ydoc["future"] = future = Map()

    # components
    app = UI(history, future, name)
    
    async with anyio.create_task_group() as tg:
        async with (
            websockets.connect("ws://localhost:8000") as websocket,
            ElvaProvider({"test": ydoc}, websocket) as provider
        ):
            await app.run_async()

if __name__ == "__main__":
    anyio.run(main, sys.argv[1])
    #ydoc = Doc()
    #app = Chat(sys.argv[1], ydoc)
    #app.run()
