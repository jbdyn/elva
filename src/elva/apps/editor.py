import logging
import sys
from pathlib import Path

import anyio
import click
import tomli_w
import websockets.exceptions as wsexc
from pycrdt import Doc, Text
from rich.text import Text as RichText
from textual.app import App
from textual.binding import Binding
from textual.widgets import Button

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from elva.auth import basic_authorization_header
from elva.log import LOGGER_NAME, DefaultFormatter
from elva.provider import ElvaWebsocketProvider, WebsocketProvider
from elva.renderer import TextRenderer
from elva.store import SQLiteStore
from elva.utils import FILE_SUFFIX, gather_context_information
from elva.widgets.config import (
    ConfigPanel,
    PathInputView,
    PathSuggester,
    QRCodeView,
    RadioSelectView,
    StatusBar,
    SwitchView,
    TextInputView,
    URLInputView,
    WebsocketsURLValidator,
)
from elva.widgets.screens import ErrorScreen
from elva.widgets.textarea import YTextArea

log = logging.getLogger(__name__)

LOG_LEVEL_MAP = dict(
    FATAL=logging.FATAL,
    ERROR=logging.ERROR,
    WARNING=logging.WARNING,
    INFO=logging.INFO,
    DEBUG=logging.DEBUG,
)

LANGUAGES = {
    "py": "python",
    "md": "markdown",
    "sh": "bash",
    "js": "javascript",
    "rs": "rust",
    "yml": "yaml",
}


def encode_content(data):
    return tomli_w.dumps(data)


class UI(App):
    CSS_PATH = "editor.tcss"

    BINDINGS = [Binding("ctrl+s", "save")]
    BINDINGS = [Binding("ctrl+r", "render")]

    def __init__(self, config: dict):
        self.config = c = config

        ansi_color = c.get("ansi_color")
        super().__init__(ansi_color=ansi_color if ansi_color is not None else False)

        self.store_config = set(
            [
                "identifier",
                "file_path",
            ]
        )
        self.provider_config = set(
            [
                "identifier",
                "server",
                "messages",
                "user",
                "password",
            ]
        )
        self.renderer_config = set(
            [
                "render_path",
                "auto_render",
            ]
        )
        self.log_config = set(
            [
                # level is always set, regardless whether it has changed or nog
                "log_path",
            ]
        )

        self.components = dict()

        # document structure
        self.ydoc = Doc()
        self.ytext = Text()
        self.ydoc["ytext"] = self.ytext

        self._language = c.get("language")

    # on posted message ConfigPanel.Applied
    async def on_config_panel_applied(self, message):
        changed = message.changed
        config = message.config

        log.setLevel(config["level"])

        if not changed.isdisjoint(self.log_config):
            log_path = config["log_path"]

            for handler in log.handlers[:]:
                log.removeHandler(handler)

            status_label = self.query_one("#logger")

            if log_path is not None and log_path.suffixes and not log_path.is_dir():
                handler = logging.FileHandler(log_path)
                handler.setFormatter(DefaultFormatter())
                log.addHandler(handler)
                status_label.variant = "success"
            else:
                status_label.variant = "default"

        if not changed.isdisjoint(self.store_config):
            store_config = dict((key, config[key]) for key in self.store_config)
            path = store_config.pop("file_path")

            status_label = self.query_one("#store")

            if (
                path is not None  #  rely on lazy evaluation
                and path.suffixes  # effectively meaning is_file(), but is independent of existence
                and not path.is_dir()
                and store_config["identifier"]
            ):
                store_config["path"] = path
                store = SQLiteStore(self.ydoc, **store_config)
                self.run_worker(
                    store.start(),
                    group="store",
                    exclusive=True,
                    exit_on_error=False,
                )
                await store.started.wait()
                status_label.variant = "success"
                self.components["store"] = store
            else:
                try:
                    self.components.pop("store")
                except KeyError:
                    pass
                self.workers.cancel_group(self, "store")
                status_label.variant = "default"

        if not changed.isdisjoint(self.renderer_config):
            renderer_config = dict((key, config[key]) for key in self.renderer_config)
            path = renderer_config.pop("render_path")
            renderer_config["path"] = path
            status_label = self.query_one("#renderer")

            if path is not None and path.suffix and not path.is_dir():
                renderer = TextRenderer(self.ytext, **renderer_config)
                self.run_worker(
                    renderer.start(),
                    group="renderer",
                    exclusive=True,
                    exit_on_error=False,
                )
                await renderer.started.wait()
                status_label.variant = "success"
            else:
                self.workers.cancel_group(self, "renderer")
                status_label.variant = "default"

        if not changed.isdisjoint(self.provider_config):
            provider_config = dict((key, config[key]) for key in self.provider_config)
            self.messages = provider_config.pop("messages")
            Provider = self.get_provider()

            user = provider_config.pop("user")
            password = provider_config.pop("password") or ""
            if user:
                self.basic_authorization_header = basic_authorization_header(
                    user, password
                )
            else:
                self.basic_authorization_header = None

            status_label = self.query_one("#provider")

            if provider_config["identifier"] and provider_config["server"]:
                provider = Provider(self.ydoc, **provider_config)
                self.run_worker(
                    provider.start(),
                    group="provider",
                    exclusive=True,
                    exit_on_error=False,
                )
                await provider.started.wait()
                status_label.variant = "success"
            else:
                self.workers.cancel_group(self, "provider")
                status_label.variant = "default"

    def get_provider(self):
        match self.messages:
            case "yjs" | None:
                Provider = WebsocketProvider
            case "elva":
                Provider = ElvaWebsocketProvider

        return Provider

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
        async with anyio.create_task_group() as self.task_group:
            for component in self.components.values():
                await self.task_group.start(component.start)
            self.task_group.start_soon(anyio.sleep_forever)

    async def on_mount(self):
        self.query_one(ConfigPanel).add_class("hidden")
        # self.run_worker(self.run_components())
        # check existence of files before anything is changed on disk
        # if self.render_path is not None:
        #    try:
        #        no_file = not self.file_path.exists()
        #    except Exception:
        #        no_file = True
        #    if self.render_path.exists() and no_file:
        #        async with await anyio.open_file(self.render_path, "r") as file:
        #            text = await file.read()
        #            self.ytext += text

    async def on_unmount(self):
        ...
        # async with anyio.create_task_group() as tg:
        #    for component in self.components.values():
        #        tg.start_soon(component.stopped.wait)
        # await self.workers.wait_for_complete()

    def compose(self):
        c = self.config

        yield YTextArea(
            self.ytext,
            tab_behavior="indent",
            show_line_numbers=True,
            id="editor",
            language=self.language,
        )

        identifier = c.get("identifier")
        server = c.get("server")
        messages = c.get("messages")

        qr_label = (
            encode_content(
                dict(identifier=identifier, server=server, messages=messages)
            )
            if all(map(lambda x: x is not None, [identifier, server, messages]))
            else None
        )

        yield ConfigPanel(
            [
                QRCodeView(
                    qr_label,
                    name="share",
                    id="view-share",
                ),
                TextInputView(
                    value=identifier,
                    name="identifier",
                    id="view-identifier",
                ),
                URLInputView(
                    value=server,
                    name="server",
                    id="view-server",
                    validators=WebsocketsURLValidator(),
                    validate_on=["changed"],
                ),
                RadioSelectView(
                    list(zip(["yjs", "elva"], ["yjs", "elva"])),
                    value=messages,
                    name="messages",
                    id="view-messages",
                ),
                TextInputView(
                    value=c.get("name"),
                    name="name",
                ),
                TextInputView(
                    value=c.get("user"),
                    name="user",
                ),
                TextInputView(
                    value=c.get("password"),
                    name="password",
                    password=True,
                ),
                PathInputView(
                    value=c.get("file_path"),
                    suggester=PathSuggester(),
                    name="file_path",
                ),
                PathInputView(
                    value=c.get("render_path"),
                    suggester=PathSuggester(),
                    name="render_path",
                ),
                SwitchView(
                    value=c.get("auto_render"),
                    name="auto_render",
                    animate=False,
                ),
                PathInputView(
                    value=c.get("log_path"),
                    suggester=PathSuggester(),
                    name="log_path",
                ),
                RadioSelectView(
                    list(LOG_LEVEL_MAP.items()),
                    value=c.get("level"),
                    name="level",
                ),
            ],
            label="X - Cut, C - Copy, S - Save",
        )

        with StatusBar():
            yield Button("=", id="config")
            yield Button("P", id="provider")
            yield Button("S", id="store")
            yield Button("R", id="renderer")
            yield Button("L", id="logger")

    def on_button_pressed(self, message):
        button = message.button
        match button.id:
            case "config":
                self.query_one(ConfigPanel).toggle_class("hidden")
            case "provider":
                if button.variant == "success":
                    self.workers.cancel_group("provider")
                else:
                    if self.components.get("provider"):
                        self.workers.run_worker(
                            self.components["provider"].start(),
                            group="provider",
                            exclusive=True,
                            exit_on_error=False,
                        )

    def on_config_view_saved(self, message):
        c = self.query_one(ConfigPanel).state
        file_path = c.get("file_path")
        if file_path is not None and file_path.suffix and not file_path.is_dir():
            SQLiteStore.set_metadata(file_path, {message.name: message.value})

    def on_config_view_changed(self, message):
        if message.name in ["identifier", "server", "messages"]:
            self.update_qrcode()

    def update_qrcode(self):
        identifier = self.query_one("#view-identifier").value
        server = self.query_one("#view-server").value
        messages = self.query_one("#view-messages").value

        content = encode_content(
            dict(identifier=identifier, server=server, messages=messages)
        )
        self.query_one("#view-share").value = content

    def action_render(self):
        if self.render_path is not None:
            self.run_worker(self.renderer.write())

            # the user explicitly wants this to be rendered,
            # so also enable the auto-rendering on closing
            self.renderer.render = True

    def action_save(self): ...

    @property
    def language(self):
        c = self.config
        file_path = c.get("file_path")
        if file_path is not None and file_path.suffix:
            suffix = "".join(file_path.suffixes).split(FILE_SUFFIX)[0].removeprefix(".")
            if str(file_path).endswith(suffix):
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
        else:
            return self._language


@click.command()
@click.option(
    "--auto-render",
    "auto_render",
    is_flag=True,
    help="Enable rendering of the data file.",
)
@click.option(
    "--apply",
    "apply",
    is_flag=True,
    help="Apply the config on startup.",
)
@click.option(
    "--ansi-color",
    "ansi_color",
    is_flag=True,
    help="Use the terminal ANSI colors for the Textual colortheme.",
)
@click.argument(
    "file",
    required=False,
    type=click.Path(path_type=Path, dir_okay=False),
)
@click.pass_context
def cli(
    ctx: click.Context,
    auto_render: bool,
    apply: bool,
    ansi_color: bool,
    file: None | Path,
):
    """Edit text documents collaboratively in real-time."""

    c = ctx.obj

    # gather info
    gather_context_information(ctx, file=file, app="editor")

    if c.get("auto_render") is None or auto_render:
        # the flag has been explicitly set by the user
        c["auto_render"] = auto_render
    c["apply"] = apply
    c["ansi_color"] = ansi_color

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
    ui = UI(c)
    ui.run()


if __name__ == "__main__":
    cli()
