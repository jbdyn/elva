from textual.app import App
from textual.widget import Widget
from textual.widgets import Input, Static, ListView, ListItem, Label
from textual.containers import VerticalScroll, Container, Horizontal, Vertical, HorizontalScroll
from textual.reactive import reactive

from pycrdt import Doc, Array, Text, Map
from pycrdt.text import TextEvent
from pycrdt.array import ArrayEvent
from pycrdt.map import MapEvent
from elva.providers import get_websocket_like_elva_provider
import websockets
import anyio
import copy
import uuid

from functools import partial
import sys
from .editor import YTextArea

from pycrdt_websocket import WebsocketProvider

import click
from elva.click_utils import lazy_group, get_option_callback_check_in_list, lazy_app_cli


class Message(Widget):
    content = reactive("")

    def __init__(self, author, **kwargs):
        self.author = author
        self.content_field = Static(self.content, classes="field content")
        super().__init__(**kwargs)

    def on_mount(self):
        self.mount(self.content_field)

    def watch_content(self, content):
        self.content_field.update(content)
 

class MessageList(VerticalScroll, can_focus_children=False):
    def __init__(self, messages, username, show_self=True, **kwargs):
        super().__init__(**kwargs)
        self.messages = messages
        self.messages.observe(self.array_callback)
        self.username = username
        self.show_self = show_self
    
    def on_mount(self):
        if isinstance(self.messages, Array):
            for message in self.messages:
                 author = message["author"]
                 text = message["text"]
                 self.log("> AUTHOR:", author)
                 self.log("> TEXT:", text)
                 if not self.show_self and author == self.username:
                     continue
                 widget = Horizontal(id="id" + message["id"].replace("-", ""), classes="message")
                 self.mount(widget)
                 text_field = Static(str(text), classes="field content")
                 author_field = Static(author, classes="field author")
                 widget.mount_all([author_field, text_field])
                 text.observe(partial(self.text_callback, widget=text_field, author=author)) 
        elif isinstance(self.messages, Map):
            for key, message in self.messages.items():
                 author = message["author"]
                 text = message["text"]
                 self.log("> AUTHOR:", author)
                 self.log("> TEXT:", text)
                 if not self.show_self and author == self.username:
                     continue
                 widget = Horizontal(id="id" + message["id"].replace("-", ""), classes="message")
                 self.mount(widget)
                 text_field = Static(str(text), classes="field content")
                 author_field = Static(author, classes="field author")
                 widget.mount_all([author_field, text_field])
                 text.observe(partial(self.text_callback, widget=text_field, author=author)) 
           

    def text_callback(self, event, widget, author):
        self.log("> TEXT ", widget, " changed: ", event)
        widget.update(str(event.target))

    def array_callback(self, event):
        if isinstance(event, ArrayEvent):
            self.log("> ARRAY changed: ", event)
            for delta in event.delta:
                retain = 0
                for action, var in delta.items():
                    if action == 'retain':
                        retain = var
                    elif action == 'insert':
                        for message in var:
                            self.log("> MESSAGE:", message, type(message))
                            author = message["author"]
                            text = message["text"]
                            self.log("> AUTHOR:", author)
                            self.log("> TEXT:", text)
                            if not self.show_self and author == self.username:
                                continue
                            widget = Horizontal(id="id" + message["id"].replace("-", ""), classes="message")
                            self.mount(widget)
                            text_field = Static(str(text), classes="field content")
                            author_field = Static(author, classes="field author")
                            widget.mount_all([author_field, text_field])
                            text.observe(partial(self.text_callback, widget=text_field, author=author)) 
                    elif action == 'delete':
                        message = self.children[retain]
                        if not self.show_self and message.author == self.username:
                            continue
                        message.remove()

        elif isinstance(event, MapEvent):
            self.log("> MAP changed: ", event)
            for key, change in event.keys.items():
                action = change["action"]
                if action == 'add':
                    message = change["newValue"]
                    self.log("> MESSAGE ID", message["id"])
                    author = message["author"]
                    text = message["text"]
                    self.log("> AUTHOR:", author)
                    self.log("> TEXT:", text)
                    if not self.show_self and author == self.username:
                        continue
                    widget = Horizontal(id="id" + message["id"].replace("-", ""), classes="message")
                    self.mount(widget)
                    text_field = Static(str(text), classes="field content")
                    author_field = Static(author, classes="field author")
                    widget.mount_all([author_field, text_field])
                    text.observe(partial(self.text_callback, widget=text_field, author=author)) 
                elif action == 'delete':
                    try:
                        widget = self.query_one("#id" + key.replace("-", ""))
                        widget.remove()
                    except:
                        pass
                    

class Chat(App):

    CSS_PATH = "chat.tcss"

    BINDINGS = [
        ("ctrl+s", "send", "Send currently composed message")
    ]

    def __init__(self, username, ydoc):
        super().__init__()
        self.username = username
        self.ydoc = ydoc
        self.history = self.ydoc["history"] = Array()
        self.future = self.ydoc["future"] = Map()
        self.future.observe(self.future_callback)
        self.future_length = 0
        self.message = None
        self.message_text = None
        self.message_id = None
        self.message_editor = None
        self.message_editor_container = None

    def future_callback(self, event):
        length = len(event.target)
        self.log("> FUTURE CALLBACK:", event, length)
        if self.future_length == 0 and length > 0:
            self.mount(MessageList(self.future, self.username, show_self=False, id="future"))
            self.future_length = length
        elif self.future_length > 0 and length == 0:
            self.query_one("#future").remove()
            self.future_length = length

    def compose(self):
        yield MessageList(self.history, self.username, id="history")

    def on_key(self, event):
        self.log("> got key event: ", event)
        if self.message is None and event.is_printable:
            self.message_id = str(uuid.uuid4())
            self.log("> MESSAGE ID:", self.message_id)
            self.message_text = Text(event.character)
            premap = dict(text=self.message_text, author=self.username, id=self.message_id)
            self.message = Map(premap)
            self.future[self.message_id] = self.message
            self.message_editor = YTextArea(self.message_text, id="editor")
            self.mount(self.message_editor)
            self.message_editor.show_line_numbers = False
            self.message_editor.focus()

        if event.is_printable:
            self.message_editor.focus()

        if str(self.message_text) == '' and event.key != "ctrl+s":
            self.message_editor.remove()
            self.future.pop(self.message_id)
            self.message_editor = None
            self.log("> MESSAGE ID: ", self.message_id)
            self.message_index = None
            self.message_text = None
            self.message = None

    def action_send(self):
        if (
            self.message is not None and
            self.message_id is not None and
            self.message_editor is not None and
            self.message_text is not None
        ):
            # buggy
            #pop_text = str(self.future.pop(self.message_index))

            # copy message content
            message_text = Text(str(self.message["text"]))
            message = Map(dict(text=message_text, author=self.message["author"], id=self.message["id"]))
            self.future.pop(self.message_id)
            self.history.append(message)
            self.message_editor.remove()
            self.message_editor = None
            self.message_index = None
            self.message_text = None
            self.message = None

UUID = "test"
REMOTE_URI = "wss://example.com/sync/"
LOCAL_URI = f"ws://localhost:8000/{UUID}"


async def run(name: str, ydoc: Doc=Doc(), uri: str=LOCAL_URI, Provider=WebsocketProvider):
    app = Chat(name, ydoc)
    async with (
        websockets.connect(uri) as websocket,
        Provider(ydoc, websocket)
    ):
        await app.run_async()


@lazy_app_cli()
@click.argument("name", required=True)
def cli(name: str, server: str, uuid: str, provider, remote_websocket_server: str, local_websocket_host: str, local_websocket_port: int):
    if server == "remote":
        # connect to the remote websocket server directly, without using the metaprovider
        uri = remote_websocket_server
        Provider = get_websocket_like_elva_provider(uuid)
    elif server == "local":
        # connect to the local metaprovider
        uri = f"ws://{local_websocket_host}:{local_websocket_port}/{uuid}"
        Provider = WebsocketProvider
    else:
        raise Exception("No valid server argument was given!")

    ydoc = Doc()
    anyio.run(run, name, ydoc, uri, Provider)

if __name__ == "__main__":
    cli()

    #ydoc = Doc()
    #app = Chat(sys.argv[1], ydoc)
    #app.run()