import logging
import uuid
from pathlib import Path

import anyio
import click
from pycrdt import Doc, Text
from textual.app import App
from textual.binding import Binding
from textual.widgets import Label, TextArea

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


class YTextAreaParser(TextEventParser):
    def __init__(self, ytext, ytext_area):
        super().__init__()
        self.ytext = ytext
        self.ytext_area = ytext_area

    async def run(self):
        self.ytext.observe(self.callback)
        await super().run()

    def callback(self, event):
        #self._task_group.start_soon(self.parse, event)
        self.parse_nowait(event)

    def location(self, index):
        return self.ytext_area.document.get_location_from_index(index)

    async def on_insert(self, range_offset, insert_value):
        start = self.location(range_offset)
        self.ytext_area.insert(insert_value, start)

    async def on_delete(self, range_offset, range_length):
        start = self.location(range_offset)
        end = self.location(range_offset + range_length)
        self.ytext_area.delete(start, end, maintain_selection_offset=True)



class YTextArea(TextArea):
    def __init__(self, ytext, **kwargs):
        super().__init__(**kwargs)
        self.ytext = ytext

    @property
    def slice(self):
        return self.get_slice_from_selection(self.selection)

    def get_slice_from_selection(self, selection):
        start, end = selection
        return sorted([self.document.get_index_from_location(loc) for loc in (start, end)])

    def on_mount(self):
        self.load_text(str(self.ytext))

    async def on_key(self, event) -> None:
        """Handle key presses which correspond to document inserts."""
        log.debug(f"got event {event}")
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

            istart, iend = self.slice
            self.ytext[istart:iend] = insert

    async def on_paste(self, event):
        # do not also call `on_paste` on the parent class,
        # which would trigger another paste
        # directly into the TextArea document (and thus again into the YText)
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


class UI(App):
    CSS_PATH = "editor.tcss"

    BINDINGS = [
        Binding("ctrl+s", "save")
    ]

    def __init__(self, filename, uri, Provider: ElvaProvider = ElvaProvider):
        super().__init__()
        self.filename = filename

        # document structure
        self.ydoc = Doc()
        self.ytext = Text()
        self.ydoc["ytext"] = self.ytext

        # widgets
        self.ytext_area = YTextArea(self.ytext, tab_behavior='indent', show_line_numbers=True, id="editor")

        # components
        self.store = SQLiteStore(self.ydoc, filename)
        self.parser = YTextAreaParser(self.ytext, self.ytext_area)
        self.renderer = TextRenderer(self.ytext, filename)
        self.provider = Provider({filename: self.ydoc}, uri)
        self.components = [
            self.renderer,
            self.store,
            self.parser,
            self.provider,
        ]

        # other stuff
        self.set_language()

    async def run_components(self):
        async with anyio.create_task_group() as self.tg:
            for component in self.components:
                await self.tg.start(component.start)

    async def on_mount(self):
        # check existence of files before anything is changed on disk
        path = Path(self.filename)
        db_path = Path(self.filename + ".y")
        if path.exists() and not db_path.exists():
            add_content = True
            async with await anyio.open_file(path, "r") as file:
                text = await file.read()
        else:
            add_content = False

        # run components
        self.run_worker(self.run_components())

        # wait for the components to have started
        async with anyio.create_task_group() as tg:
            for component in self.components:
                tg.start_soon(component.started.wait)

        # add content of pre-existing text files
        if add_content:
            log.debug("waiting for store to be initialized")
            await self.store.wait_running()
            log.debug("reading in already present text file")
            self.ytext += text

    async def on_unmount(self):
        async with anyio.create_task_group() as tg:
            for component in self.components:
                tg.start_soon(component.stopped.wait)

    def compose(self):
        yield self.ytext_area
        yield Label(f"file: {self.filename}")

    def action_save(self):
        self.run_worker(self.renderer.write())

    def set_language(self):
        extension = self.filename.split(".")[-1]
        if extension == self.filename:
            log.info("continuing without syntax highlighting")
        else:
            try:
                self.ytext_area.language = LANGUAGES[extension]
            except Exception:
                log.info(f"no syntax highlighting available for extension '{extension}'")


@click.group(invoke_without_command=True)
@click.argument("file", required=False)
@click.pass_context
def cli(ctx: click.Context, file: str):
    """collaborative editor"""

    uri = ctx.obj['uri']
    provider = ctx.obj['provider']

    if file is None:
        file = str(uuid.uuid4())

    # run app
    ui = UI(file, uri, provider)
    ui.run()

if __name__ == "__main__":
    cli()
