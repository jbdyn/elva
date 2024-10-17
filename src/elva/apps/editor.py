iport logging
import uuid
from dataclasses import dataclass
from pathlib import Path

import anyio
import click
import websockets.exceptions as wsexc
from pycrdt import Doc, Text
from rich.text import Text as RichText
from textual.app import App
from textual.binding import Binding
from textual.containers import Container, Grid, Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Input, Label, RadioButton, RadioSet, Select, Switch

from elva.auth import basic_authorization_header
from elva.log import LOGGER_NAME, DefaultFormatter
from elva.provider import ElvaWebsocketProvider, WebsocketProvider
from elva.renderer import TextRenderer
from elva.store import SQLiteStore
from elva.utils import FILE_SUFFIX, gather_context_information
from elva.widgets.screens import CredentialScreen, ErrorScreen
from elva.widgets.textarea import YTextArea

log = logging.getLogger(__name__)

LANGUAGES = {
    "py": "python",
    "md": "markdown",
    "sh": "bash",
    "js": "javascript",
    "rs": "rust",
    "yml": "yaml",
}


class ConfigPanel(Container):
    class ConfigSaved(Message):
        def __init__(self, old, new, changed):
            super().__init__()
            self.old = old
            self.new = new
            self.changed = changed

    def __init__(self, config):
        super().__init__()
        self.config = config

    @property
    def state(self):
        return dict((c.name, c.value) for c in self.config)

    @state.setter
    def state(self, new):
        for c in self.config:
            c.widget.value = new.get(c.name)

    def compose(self):
        with Grid():
            with VerticalScroll():
                for c in self.config:
                    c.border_title = c.name
                    yield c
            with Grid():
                yield Button("Apply", id="apply")
                yield Button("Reset", id="reset")

    def on_mount(self):
        self.old = self.state

    def post_changed_config(self):
        new = self.state
        changed = set(c.name for c in self.config if self.old[c.name] != new[c.name])
        self.post_message(self.ConfigSaved(self.old, new, changed))
        self.old = new

    def on_input_submitted(self, message):
        self.post_changed_config()

    def on_button_pressed(self, message):
        match message.button.id:
            case "apply":
                self.post_changed_config()
            case "reset":
                self.state = self.old


class ConfigView(Widget):
    def __init__(self, widget):
        super().__init__()
        self.widget = widget

    def compose(self):
        yield self.widget

    @property
    def name(self):
        return self.widget.name

    @property
    def value(self):
        return self.widget.value


class RadioSelect(Container):
    def __init__(self, options, value, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.options = options
        self._init_value = value
        self.buttons = dict(
            (option, RadioButton(option, value=(option == value), name=option))
            for option in options
        )

        self.radio_set = RadioSet()

    def compose(self):
        with self.radio_set:
            for button in self.buttons.values():
                yield button

    @property
    def value(self):
        return self.radio_set.pressed_button.name

    @value.setter
    def value(self, value):
        self.buttons[value].value = True


class TextInputView(ConfigView):
    def __init__(self, *args, **kwargs):
        widget = Input(*args, **kwargs)
        super().__init__(widget)

    def compose(self):
        with Grid():
            yield self.widget
            yield Button("X", classes="clear")

    def on_button_pressed(self, message):
        self.widget.clear()


class UI(App):
    CSS_PATH = "editor.tcss"

    BINDINGS = [Binding("ctrl+s", "save")]
    BINDINGS = [Binding("ctrl+r", "render")]

    def __init__(
        self,
        file_path: None | Path = None,
        render_path: None | Path = None,
        server: None | Path = None,
        identifier: None | Path = None,
        messages: str = "yjs",
        user: str | None = None,
        password: str | None = None,
        auto_render: bool = False,
    ):
        super().__init__()

        self.messages = messages

        # ConfigPanel widgets
        self.config_widgets = [
            TextInputView(
                value=identifier,
                name="identifier",
            ),
            TextInputView(value=server, name="server"),
            ConfigView(
                RadioSelect(
                    ["yjs", "elva"],
                    value=messages,
                    name="messages",
                )
            ),
            TextInputView(value=user, name="user"),
            TextInputView(
                value=password,
                name="password",
                password=True,
                classes="config",
            ),
            ConfigView(
                Input(
                    value=file_path,
                    name="file_path",
                    classes="config",
                )
            ),
            ConfigView(
                Input(
                    value=render_path,
                    name="render_path",
                    classes="config",
                )
            ),
            ConfigView(
                Switch(
                    value=auto_render,
                    name="auto_render",
                    animate=False,
                    classes="config",
                )
            ),
        ]

        self.config_panel = ConfigPanel(self.config_widgets)

        self.store_config = set(["identifier", "file_path"])
        self.provider_config = set(
            ["identifier", "server", "messages", "user", "password"]
        )
        self.renderer_config = set(["render_path", "auto_render"])

        self.components = dict()

        # document structure
        self.ydoc = Doc()
        self.ytext = Text()
        self.ydoc["ytext"] = self.ytext

        # widgets
        # language = self._get_language()
        self.ytext_area = YTextArea(
            self.ytext,
            tab_behavior="indent",
            show_line_numbers=True,
            id="editor",
            #    language=language,
        )

    # on posted message ConfigPanel.ConfigSaved
    def on_config_panel_config_saved(self, message):
        self.log(message)
        changed = message.changed
        config = message.new

        if not changed.isdisjoint(self.store_config):
            store_config = dict([(key, config.get(key)) for key in self.store_config])
            store_config["path"] = Path(store_config.pop("file_path"))
            self.log("STORE", store_config)
            store = SQLiteStore(self.ydoc, **store_config)
            self.run_worker(store.start(), group="store", exclusive=True)

        if not changed.isdisjoint(self.renderer_config):
            renderer_config = dict(
                [(key, config.get(key)) for key in self.renderer_config]
            )
            self.log("RENDERER", renderer_config)
            renderer_config["path"] = Path(renderer_config.pop("render_path"))
            renderer_config["render"] = bool(renderer_config["render"])
            renderer = TextRenderer(self.ytext, **renderer_config)
            self.run_worker(renderer.start(), group="renderer", exclusive=True)

        if not changed.isdisjoint(self.provider_config):
            Provider = self.get_provider()
            provider_config = dict(
                [(key, config.get(key)) for key in self.provider_config]
            )
            self.messages = provider_config.pop("messages")
            user = provider_config.pop("user")
            password = provider_config.pop("password")
            provider_config["additional_headers"] = basic_authorization_header(
                user, password
            )
            self.log("PROVIDER", provider_config)
            provider = Provider(self.ydoc, **provider_config)
            self.run_worker(provider.start(), group="provider", exclusive=True)

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
        ...
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
        async with anyio.create_task_group() as tg:
            for component in self.components.values():
                tg.start_soon(component.stopped.wait)

    def compose(self):
        with Horizontal():
            yield self.ytext_area
            yield self.config_panel

    def action_render(self):
        if self.render_path is not None:
            self.run_worker(self.renderer.write())

            # the user explicitly wants this to be rendered,
            # so also enable the auto-rendering on closing
            self.renderer.render = True

    def action_save(self): ...

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
        render,
    )
    ui.run()


if __name__ == "__main__":
    cli()
