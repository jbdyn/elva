from textual.app import App
from textual.message import Message
from textual.widgets import TextArea, Label
from textual.events import Paste
from rich.text import Text as RichText
import time
import anyio
from pycrdt import Doc, Text
from functools import partial
import os

from websockets import connect
from pycrdt_websocket import WebsocketProvider
from elva.providers import ElvaProvider
import sys
import uuid
import click
from elva.utils import load_ydoc, save_ydoc

class YTextArea(TextArea):
    def __init__(self, ytext, **kwargs):
        super().__init__(**kwargs)
        self.ytext = ytext
        start = self.document.get_location_from_index(0)
        self.insert(str(ytext), start)
        self.ytext.observe(self.callback)

    def callback(self, event):
        self.log(">>> YTextEvent:", event)
        delta = event.delta
        start = self.document.get_location_from_index(0)
        for d in delta:
            self.log(">>> Delta:", list(d.items())[0])
            action, var = list(d.items())[0]

            # depends on assumption that 'retain' always comes before
            # 'insert' or 'delete'
            if action == 'retain':
                start = self.document.get_location_from_index(var)
            elif action == 'insert':
                self.insert(var, start)
            elif action == 'delete':
                istart = self.document.get_index_from_location(start)
                end = self.document.get_location_from_index(istart + var)
                self.delete(start, end, maintain_selection_offset=True)
            else:
                raise Exception(f"Unknown action '{action}' from YTextEvent")

    @property
    def slice(self):
        return self.get_slice_from_selection(self.selection)

    def get_slice_from_selection(self, selection):
        start, end = selection
        return sorted([self.document.get_index_from_location(loc) for loc in (start, end)])

    def on_key(self, event) -> None:
        """Handle key presses which correspond to document inserts."""
        self.log(">>> Key:", event)
        key = event.key
        insert_values = {
            #"tab": " " * self._find_columns_to_next_tab_stop(),
            "tab": "\t",
            "enter": "\n",
        }
        self._restart_blink()
        if event.is_printable or key in insert_values:
            event.stop()
            event.prevent_default()
            insert = insert_values.get(key, event.character)
            # `insert` is not None because event.character cannot be
            # None because we've checked that it's printable.
            assert insert is not None
            #start, end = self.selection
            #self.replace(insert, start, end, maintain_selection_offset=False)

            istart, iend = self.slice
            self.ytext[istart:iend] = insert
        
            self.log(self.text)
            self.log(self.ytext.to_py())


    async def on_paste(self, event):
        # do not also call `on_paste` on the parent class,
        # which would trigger another paste
        # directly into the TextArea document (and not the YText)
        event.prevent_default()

        istart, iend = self.slice
        self.ytext[istart:iend] = event.text

    async def action_delete_left(self):
        selection = self.selection
        start, end = selection

        if selection.is_empty:
            start = self.get_cursor_left_location()

        istart, iend = self.get_slice_from_selection((start, end))
        del self.ytext[istart:iend]

    async def action_delete_right(self):
        selection = self.selection
        start, end = selection

        if selection.is_empty:
            end = self.get_cursor_right_location()

        istart, iend = self.get_slice_from_selection((start, end))
        del self.ytext[istart:iend]

# delete_word_left
# delete_word_right
# delete_line
# delete_to_start_of_line
# delete_to_end_of_line

class Editor(App):
    def __init__(self, ydoc=None, identifier=None):
        super().__init__()
        self.ydoc = ydoc if ydoc is not None else Doc()
        self.identifier = identifier
        try:
            self.ytext = self.ydoc["ytext"]
        except KeyError as e:
            self.log(e)
            self.log("Adding an empty YText data type.")
            self.ydoc["ytext"] = self.ytext = Text()
        self.text_area = YTextArea(self.ydoc)

    def compose(self):
        yield self.text_area
        yield Label(f"id: {self.identifier}")

async def run(identifier=None, uri="ws://localhost:8000/"):
    if not identifier:
        identifier = str(uuid.uuid4())
    path = identifier + ".y" if not identifier.endswith(".y") else identifier
    ydoc = Doc()
    app = Editor(ydoc, identifier)
    if os.path.exists(path):
        try:
            load_ydoc(ydoc, path=path)
        except Exception as e:
            print(e)

    async with (
        connect(uri+identifier) as websocket,
        WebsocketProvider(ydoc, websocket),
    ):
        await app.run_async()

    try:
        save_ydoc(ydoc, path=path)
    except Exception as e:
        print(e)


@click.command()
@click.argument("name", required=False)
@click.option("--uri", "-u", "uri", default="ws://localhost:8000/", show_default=True)
def main(name, uri):
    anyio.run(run, name, uri)

if __name__ == "__main__":
    main()
