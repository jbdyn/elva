import logging
from pathlib import Path

import anyio
import click
import websockets.exceptions as wsexc
from pycrdt import Doc, Text
from rich.text import Text as RichText
from textual.app import App
from textual.binding import Binding
from textual.containers import Grid
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static, TextArea

from elva.auth import basic_authorization_header
from elva.component import LOGGER_NAME
from elva.log import DefaultFormatter
from elva.parser import TextEventParser
from elva.provider import ElvaWebsocketProvider, WebsocketProvider
from elva.renderer import TextRenderer
from elva.store import SQLiteStore
from elva.utils import FILE_SUFFIX, gather_context_information

LOGGER_NAME.set(__name__)
log = logging.getLogger(__name__)

LANGUAGES = {
    "py": "python",
    "md": "markdown",
    "sh": "bash",
    "js": "javascript",
    "rs": "rust",
    "yml": "yaml",
}


class CredentialScreen(ModalScreen):
    def __init__(self, options, body=None, username=None):
        super().__init__(id="credentialscreen")
        self.options = options
        self.body = Static(RichText(body, justify="center"), id="body")

        self.username = Input(placeholder="user name", id="username")
        if username is not None:
            self.username.value = username
        self.password = Input(placeholder="password", password=True, id="password")

    def compose(self):
        with Grid(id="form"):
            yield self.body
            yield self.username
            yield self.password
            yield Button("Confirm", id="confirm")

    def on_button_pressed(self, event):
        credentials = (self.username.value, self.password.value)
        header = basic_authorization_header(*credentials)
        self.options["additional_headers"] = header
        self.dismiss(credentials)


class YTextAreaParser(TextEventParser):
    def __init__(self, ytext, ytext_area):
        super().__init__()
        self.ytext = ytext
        self.ytext_area = ytext_area
        self.btext = self.ytext_area.text.encode()

    async def run(self):
        self.ytext.observe(self.callback)
        await super().run()

    def callback(self, event):
        # self._task_group.start_soon(self.parse, event)
        self.parse_nowait(event)

    def location(self, index):
        return self.ytext_area.document.get_location_from_index(index)

    async def on_insert(self, range_offset, insert_value):
        # adapt range_offset to UTF-8 encoding
        btext_start = self.btext[:range_offset]
        btext_rest = self.btext[range_offset:]
        range_offset = len(btext_start.decode())

        # get Location and insert in TextArea
        start = self.location(range_offset)
        self.ytext_area.insert(insert_value, start)

        # update UTF-8 encoded TextArea content
        self.btext = btext_start + insert_value.encode() + btext_rest

    async def on_delete(self, range_offset, range_length):
        # adapt range_offset and range_length to UTF-8 encoding
        btext_start = self.btext[:range_offset]
        btext_range = self.btext[range_offset : range_offset + range_length]
        btext_rest = self.btext[range_offset + range_length :]
        range_offset = len(btext_start.decode())
        range_length = len(btext_range.decode())

        # get Locations and perform deletion
        start = self.location(range_offset)
        end = self.location(range_offset + range_length)
        self.ytext_area.delete(start, end, maintain_selection_offset=True)

        # update UTF-8 encoded TextArea content
        self.btext = btext_start + btext_rest


class YTextArea(TextArea):
    def __init__(self, ytext, **kwargs):
        super().__init__(**kwargs)
        self.ytext = ytext

    def get_utf8_index(self, unicode_index):
        return len(self.text[:unicode_index].encode())

    @property
    def slice(self):
        return self.get_slice_from_selection(self.selection)

    def get_slice_from_selection(self, selection):
        start, end = selection
        unicode_slice = sorted(
            [self.document.get_index_from_location(loc) for loc in (start, end)]
        )
        return tuple(
            self.get_utf8_index(unicode_index) for unicode_index in unicode_slice
        )

    def on_mount(self):
        self.load_text(str(self.ytext))

    async def on_key(self, event) -> None:
        """Handle key presses which correspond to document inserts."""
        log.debug(f"got event {event}")
        key = event.key
        insert_values = {
            # "tab": " " * self._find_columns_to_next_tab_stop(),
            "tab": "\t",
            "enter": "\n",
        }
        self._restart_blink()
        if event.is_printable or key in insert_values:
            event.stop()
            event.prevent_default()
            insert = insert_values.get(key, event.character)

            start, end = self.selection
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

    BINDINGS = [Binding("ctrl+s", "save")]

    def __init__(
        self,
        file_path: None | Path = None,
        render_path: None | Path = None,
        server: None | Path = None,
        identifier: None | Path = None,
        message_type: str = "yjs",
        user: str | None = None,
        password: str | None = None,
    ):
        super().__init__()
        self.file_path = file_path
        self.render_path = render_path
        self.identifier = identifier
        self.user = user
        self.password = password

        # document structure
        self.ydoc = Doc()
        self.ytext = Text()
        self.ydoc["ytext"] = self.ytext

        # widgets
        self.ytext_area = YTextArea(
            self.ytext, tab_behavior="indent", show_line_numbers=True, id="editor"
        )

        # components
        self.parser = YTextAreaParser(self.ytext, self.ytext_area)

        self.components = [
            self.parser,
        ]

        if file_path is not None:
            self.store = SQLiteStore(self.ydoc, identifier, file_path)
            self.components.append(self.store)

            self.identifier = self.store.identifier

        if server is not None and identifier is not None:
            match message_type:
                case "yjs":
                    Provider = WebsocketProvider
                case "elva":
                    Provider = ElvaWebsocketProvider

            self.provider = Provider(
                self.ydoc, identifier, server, on_exception=self.on_exception
            )
            # save as attribute to be able to update the response `body`
            self.credential_screen = CredentialScreen(
                self.provider.options, "", self.user
            )
            # install the screen so that unique IDs are respected
            self.install_screen(self.credential_screen, name="credential_screen")
            self.tried_auto = False
            self.tried_modal = False
            self.components.append(self.provider)

        if render_path is not None:
            self.renderer = TextRenderer(self.ytext, render_path)
            self.components.append(self.renderer)

        # other stuff
        self.set_language()

    async def on_exception(self, exc):
        match type(exc):
            case wsexc.InvalidStatus:
                if (
                    self.user is not None
                    and self.password is not None
                    # we tried this branch already with these credentials
                    and not self.tried_auto
                    # these credentials have been supplied via CredentialScreen and are incorrect,
                    # go directly to modal screen again
                    and not self.tried_modal
                ):
                    header = basic_authorization_header(self.user, self.password)
                    self.provider.options["additional_headers"] = header
                    self.tried_auto = True
                else:
                    body = exc.response.body.decode()
                    # update manually
                    self.credential_screen.body.update(RichText(body, justify="center"))
                    self.credential_screen.username.clear()
                    self.credential_screen.username.insert_text_at_cursor(self.user)
                    # push via screen name
                    await self.push_screen(
                        "credential_screen",
                        self.update_credentials,
                        # wait for connection retry after screen has been closed
                        wait_for_dismiss=True,
                    )
                    self.tried_modal = True

    def update_credentials(self, credentials):
        self.user, self.password = credentials

    async def run_components(self):
        async with anyio.create_task_group() as self.tg:
            for component in self.components:
                await self.tg.start(component.start)

    async def on_mount(self):
        # check existence of files before anything is changed on disk
        if self.render_path is not None:
            try:
                no_file = not self.file_path.exists()
            except Exception:
                no_file = True
            if self.render_path.exists() and no_file:
                add_content = True
                async with await anyio.open_file(self.render_path, "r") as file:
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
        if self.render_path is not None and add_content:
            if self.file_path is not None:
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
        yield Label(f"identifier: {self.identifier}")

    def action_save(self):
        if self.render_path is not None:
            self.run_worker(self.renderer.write())

    def set_language(self):
        if self.file_path is not None:
            suffix = (
                "".join(self.file_path.suffixes).split(FILE_SUFFIX)[0].removeprefix(".")
            )
            if str(self.file_path).endswith(suffix):
                log.info("continuing without syntax highlighting")
            else:
                try:
                    lang = LANGUAGES[suffix]
                    self.ytext_area.language = lang
                    log.info(f"enabled {lang} syntax highlighting")
                except KeyError:
                    log.info(
                        f"no syntax highlighting available for file type '{suffix}'"
                    )


@click.command()
@click.option(
    "--render",
    "-r",
    "render",
    is_flag=True,
    help="Enable rendering the file",
)
@click.argument(
    "file",
    required=False,
    type=click.Path(path_type=Path, dir_okay=False),
)
@click.pass_context
def cli(ctx: click.Context, render: bool, file: None | Path):
    """collaborative text editor"""

    c = ctx.obj

    # gather info
    gather_context_information(ctx, file)

    if not render:
        c["render"] = None

    # logging
    level = c["level"]
    log_path = c["log"]
    if level is not None and log_path is not None:
        handler = logging.FileHandler(log_path)
        handler.setFormatter(DefaultFormatter())
        log.addHandler(handler)
        log.setLevel(level)

    # run app
    ui = UI(
        c["file"],
        c["render"],
        c["server"],
        c["identifier"],
        c["message_type"],
        c["user"],
        c["password"],
    )
    ui.run()


if __name__ == "__main__":
    cli()
