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
from textual.widgets import Button, Input, Label, Static

from elva.auth import basic_authorization_header
from elva.document import YTextArea
from elva.log import LOGGER_NAME, DefaultFormatter
from elva.parser import TextEventParser
from elva.provider import ElvaWebsocketProvider, WebsocketProvider
from elva.renderer import TextRenderer
from elva.store import SQLiteStore
from elva.utils import FILE_SUFFIX, gather_context_information

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
    def __init__(self, options, body=None, user=None):
        super().__init__(classes="modalscreen", id="credentialscreen")
        self.options = options
        self.body = Static(RichText(body, justify="center"), id="body")

        self.user = Input(placeholder="user", id="user")
        self.user.value = user or ""
        self.password = Input(placeholder="password", password=True, id="password")

    def compose(self):
        with Grid(classes="form"):
            yield self.body
            yield self.user
            yield self.password
            yield Button("Confirm", classes="confirm")

    def update_and_return_credentials(self):
        credentials = (self.user.value, self.password.value)
        header = basic_authorization_header(*credentials)
        self.options["additional_headers"] = header
        self.password.clear()
        self.dismiss(credentials)

    def on_button_pressed(self, event):
        self.update_and_return_credentials()

    def key_enter(self):
        self.update_and_return_credentials()


class ErrorScreen(ModalScreen):
    def __init__(self, exc):
        super().__init__(classes="modalscreen", id="errorscreen")
        self.exc = exc

    def compose(self):
        with Grid(classes="form"):
            yield Static(
                RichText(
                    "The following error occured and the app will close now:",
                    justify="center",
                )
            )
            yield Static(RichText(str(self.exc), justify="center"))
            yield Button("OK", classes="confirm")

    def on_button_pressed(self, event):
        self.dismiss()


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


class UI(App):
    CSS_PATH = "editor.tcss"

    BINDINGS = [Binding("ctrl+s", "save")]

    def __init__(
        self,
        file_path: None | Path = None,
        render_path: None | Path = None,
        server: None | Path = None,
        identifier: None | Path = None,
        messages: str = "yjs",
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
        language = self._get_language()
        self.ytext_area = YTextArea(
            self.ytext,
            tab_behavior="indent",
            show_line_numbers=True,
            id="editor",
            language=language,
        )

        # components
        self.components = []

        if file_path is not None:
            self.store = SQLiteStore(self.ydoc, identifier, file_path)
            self.components.append(self.store)

            self.identifier = self.store.identifier

        if server is not None and identifier is not None:
            match messages:
                case "yjs" | None:
                    Provider = WebsocketProvider
                case "elva":
                    Provider = ElvaWebsocketProvider

            self.provider = Provider(self.ydoc, identifier, server)
            self.provider.on_exception = self.on_exception
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

    async def on_exception(self, exc):
        match type(exc):
            case wsexc.InvalidStatus:
                if exc.response.status_code == 401:
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
                        self.credential_screen.body.update(
                            RichText(body, justify="center")
                        )
                        self.credential_screen.user.clear()
                        self.credential_screen.user.insert_text_at_cursor(
                            self.user or ""
                        )
                        # push via screen name
                        await self.push_screen(
                            "credential_screen",
                            self.update_credentials,
                            # wait for connection retry after screen has been closed
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

    def quit_on_error(self, error):
        self.exit()

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

    def _get_language(self):
        if self.file_path is not None:
            suffix = (
                "".join(self.file_path.suffixes).split(FILE_SUFFIX)[0].removeprefix(".")
            )
            if str(self.file_path).endswith(suffix):
                log.info("continuing without syntax highlighting")
            else:
                try:
                    language = LANGUAGES[suffix]
                    return language
                    log.info(f"enabled {language} syntax highlighting")
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
    help="Enable rendering of the data file.",
)
@click.argument(
    "file",
    required=False,
    type=click.Path(path_type=Path, dir_okay=False),
)
@click.pass_context
def cli(ctx: click.Context, render: bool, file: None | Path):
    """Edit text documents collaboratively in real-time."""

    c = ctx.obj

    # gather info
    gather_context_information(ctx, file, app="editor")

    if not render:
        c["render"] = None

    # logging
    LOGGER_NAME.set(__name__)
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
        c["messages"],
        c["user"],
        c["password"],
    )
    ui.run()


if __name__ == "__main__":
    cli()
