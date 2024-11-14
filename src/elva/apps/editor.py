import logging
from copy import deepcopy
from pathlib import Path

import click
import tomli_w
from pycrdt import Doc, Text
from textual.app import App
from textual.binding import Binding
from textual.widgets import Button
from textual.worker import WorkerState
from websockets.exceptions import InvalidStatus

from elva.component import Component
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


def get_provider(self, ydoc, **config):
    try:
        msg = config.pop("messages")
    except KeyError:
        msg = None

    match msg:
        case "yjs" | None:
            provider = WebsocketProvider(ydoc, **config)
        case "elva":
            provider = ElvaWebsocketProvider(ydoc, **config)

    return provider


def encode_content(data):
    return tomli_w.dumps(data)


class FeatureStatus(Button):
    def __init__(self, params, *args, config=None, param_map=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.params = params
        self.config = self.trim(config)
        self.param_map = param_map

    def trim(self, config):
        return dict((param, config.get(param)) for param in self.params)

    def update(self, config):
        trimmed = self.trim(config)
        changed = trimmed != self.config

        if self.param_map is not None:
            for from_param, to_param in self.param_map.items():
                trimmed[to_param] = trimmed.pop(from_param)

        self.config = trimmed
        if changed:
            self.apply()

    @property
    def is_ready(self): ...

    def apply(self): ...


class LogStatus(FeatureStatus):
    @property
    def is_ready(self):
        path = self.config.get("path")
        return path is not None and len(path.suffixes) > 0 and not path.is_dir()

    def apply(self):
        if self.is_ready:
            c = self.config
            path = c.get("path")

            for handler in log.handlers[:]:
                log.removeHandler(handler)

            handler = logging.FileHandler(path)
            handler.setFormatter(DefaultFormatter())
            log.addHandler(handler)
            log.setLevel(c.get("level") or logging.INFO)
            self.variant = "success"
        else:
            self.variant = "default"


class ComponentStatus(FeatureStatus):
    component: Component

    def __init__(self, yobject, params, *args, **kwargs):
        self.yobject = yobject
        self.instance = None
        super().__init__(params, *args, **kwargs)

    def apply(self):
        if self.is_ready:
            component = self.component(self.yobject, **self.config)
            self.run_worker(component.start(), exclusive=True, exit_on_error=False)
            self.variant = "success"
        else:
            self.workers.cancel_node(self)
            self.variant = "default"

    def on_worker_state_changed(self, message):
        match message.state:
            case WorkerState.ERROR:
                self.variant = "error"
            case WorkerState.CANCELLED | WorkerState.SUCCESS:
                self.variant = "default"

    def on_button_pressed(self, message):
        if message.button.variant == "success":
            self.workers.cancel_node(self)
        else:
            self.apply()


class StoreStatus(ComponentStatus):
    component = SQLiteStore

    @property
    def is_ready(self):
        c = self.config
        path = c.get("path")
        return (
            path is not None
            and len(path.suffixes) > 0
            and not path.is_dir()
            and c.get("identifier") is not None
        )


class RendererStatus(ComponentStatus):
    component = TextRenderer

    @property
    def is_ready(self):
        path = self.config.get("path")
        return path is not None and len(path.suffixes) > 0 and not path.is_dir()


class ProviderStatus(ComponentStatus):
    component = get_provider

    @property
    def is_ready(self):
        c = self.config
        return c.get("identifier") and c.get("server")


class UI(App):
    CSS_PATH = "editor.tcss"

    BINDINGS = [Binding("ctrl+s", "save")]
    BINDINGS = [Binding("ctrl+r", "render")]

    def __init__(self, config: dict):
        self.config = c = config

        ansi_color = c.get("ansi_color")
        super().__init__(ansi_color=ansi_color if ansi_color is not None else False)

        identifier = c.get("identifier")
        server = c.get("server")
        messages = c.get("messages")

        qr = (
            encode_content(
                dict(identifier=identifier, server=server, messages=messages)
            )
            if all(map(lambda x: x is not None, [identifier, server, messages]))
            else None
        )

        c["qr"] = qr

        # document structure
        self.ydoc = Doc()
        self.ytext = Text()
        self.ydoc["ytext"] = self.ytext

        self._language = c.get("language")

    async def on_config_panel_applied(self, message):
        for status_id in ["#provider", "#store", "#renderer", "#logger"]:
            self.query_one(status_id).update(message.config)

    async def on_exception(self, exc):
        if isinstance(exc, InvalidStatus) and exc.response.status_code == 401:
            self.query_one(ConfigPanel).remove_class("hidden")
            self.query_one("#provider").variant = "error"

        # reraise to break connection loop
        raise exc

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

    def compose(self):
        c = self.config

        yield YTextArea(
            self.ytext,
            tab_behavior="indent",
            show_line_numbers=True,
            id="editor",
            language=self.language,
        )

        yield ConfigPanel(
            [
                QRCodeView(
                    c.get("qr"),
                    name="share",
                    id="view-share",
                ),
                TextInputView(
                    value=c.get("identifier"),
                    name="identifier",
                    id="view-identifier",
                ),
                URLInputView(
                    value=c.get("server"),
                    name="server",
                    id="view-server",
                    validators=WebsocketsURLValidator(),
                    validate_on=["changed"],
                ),
                RadioSelectView(
                    list(zip(["yjs", "elva"], ["yjs", "elva"])),
                    value=c.get("messages") or "yjs",
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
                    id="view-user",
                ),
                TextInputView(
                    value=c.get("password"),
                    name="password",
                    password=True,
                    id="view-password",
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
                    value=c.get("level") or LOG_LEVEL_MAP["INFO"],
                    name="level",
                ),
            ],
            label="X - Cut, C - Copy, S - Save",
        )

        with StatusBar():
            yield Button("=", id="config")
            yield ProviderStatus(
                self.ydoc,
                [
                    "identifier",
                    "server",
                    "messages",
                    "user",
                    "password",
                ],
                "P",
                config=self.config,
                id="provider",
            )
            yield StoreStatus(
                self.ydoc,
                [
                    "identifier",
                    "file_path",
                ],
                "S",
                config=self.config,
                param_map={"file_path": "path"},
                id="store",
            )
            yield RendererStatus(
                self.ytext,
                [
                    "render_path",
                    "auto_render",
                ],
                "R",
                config=self.config,
                param_map={"render_path": "path"},
                id="renderer",
            )
            yield LogStatus(
                [
                    # level is always set, regardless whether it has changed or nog
                    "log_path",
                ],
                "L",
                config=self.config,
                param_map={"log_path": "path"},
                id="logger",
            )

    def on_button_pressed(self, message):
        button = message.button
        match button.id:
            case "config":
                self.query_one(ConfigPanel).toggle_class("hidden")

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
