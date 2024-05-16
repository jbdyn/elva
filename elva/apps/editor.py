import os
import uuid
import logging

import anyio
import click
from pycrdt import Doc, Text
from textual.app import App as TextualApp
from textual.binding import Binding
from textual.widgets import Label, TextArea
from websockets import connect

import elva.logging_config
from elva.parser import TextEventParser
from elva.provider import ElvaProvider
from elva.store import SQLiteStore
from elva.renderer import TextRenderer


log = logging.getLogger(__name__)


LANGUAGES = {
    "py": "python",
    "md": "markdown",
    "sh": "bash",
    "js": "javascript",
    "rs": "rust",
    "yml": "yaml",
}


def set_language(text_area, filename):
    extension = filename.split(".")[-1]
    if extension == filename:
        log.info("continuing without syntax highlighting")
    else:
        try:
            text_area.language = LANGUAGES[extension]
        except:
            log.exception(f"no syntax highlighting available for extension '{extension}'")



class YTextArea(TextArea):
    class YTextAreaParser(TextEventParser):
        def __init__(self, ytext, ytext_area):
            super().__init__()
            self.ytext = ytext
            self.ytext.observe(self.callback)
            self.ytext_area = ytext_area
    
        def callback(self, event):
            self._task_group.start_soon(self.parse, event)
    
        def location(self, index):
            return self.ytext_area.document.get_location_from_index(index)
    
        async def on_insert(self, range_offset, insert_value):
            start = self.location(range_offset)
            self.ytext_area.insert(insert_value, start)
    
        async def on_delete(self, range_offset, range_length):
            start = self.location(range_offset)
            end = self.location(range_offset + range_length)
            self.ytext_area.delete(start, end, maintain_selection_offset=True)

    def __init__(self, ytext, **kwargs):
        super().__init__(**kwargs)
        self.ytext = ytext
        self.insert(str(ytext), (0,0))
        self.parser = self.YTextAreaParser(ytext, self)

    async def run_parser(self):
        async with anyio.create_task_group() as tg:
            await tg.start(self.parser.start)

    async def on_mount(self):
        self.run_worker(self.run_parser)

    @property
    def slice(self):
        return self.get_slice_from_selection(self.selection)

    def get_slice_from_selection(self, selection):
        start, end = selection
        return sorted([self.document.get_index_from_location(loc) for loc in (start, end)])

    async def on_key(self, event) -> None:
        """Handle key presses which correspond to document inserts."""
        self.log(f"got event {event}")
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


class UI(TextualApp):
    BINDINGS = [
        Binding("ctrl+s", "save")
    ]

    def __init__(self, ytext, filename, renderer):
        super().__init__()
        self.ytext_area = YTextArea(ytext)
        self.filename = filename
        self.renderer = renderer

    def compose(self):
        yield self.ytext_area
        yield Label(f"file: {self.filename}")

    def action_save(self):
        self.run_worker(self.renderer.write())


async def run(filename, uri):
    # YDoc struct
    ydoc = Doc()
    ytext = Text()
    ydoc["ytext"] = ytext

    # components
    store = SQLiteStore(ydoc, filename + ".y")
    renderer = TextRenderer(ytext, filename)
    ui = UI(ytext, filename, renderer)
    ytext_area = ui.ytext_area
    set_language(ytext_area, filename)
    #parser = YTextAreaParser(ytext, ytext_area)

    async with anyio.create_task_group() as tg:
        await tg.start(store.start)
        await tg.start(renderer.start)
        #await tg.start(parser.start)

        async with (
            connect(uri, logger=log) as websocket,
            ElvaProvider({filename: ydoc}, websocket),
        ):
            await ui.run_async()

        #await parser.stop()
        await renderer.stop()
        await store.stop()


@click.command()
@click.argument("name", required=False)
@click.option("--uri", "-u", "uri", default="ws://localhost:8000/", show_default=True)
def main(name, uri):

    # check arguments and sanitize
    if not name:
        name = str(uuid.uuid4())

    # run app
    anyio.run(run, name, uri)


if __name__ == "__main__":
    main()
