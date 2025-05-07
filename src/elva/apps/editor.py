"""
ELVA editor app.
"""

import logging
from pathlib import Path

import click
import tomli_w
from pycrdt import Doc, Text
from textual.app import App
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Button
from textual.worker import WorkerState
from websockets.exceptions import InvalidStatus

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
    SwitchView,
    TextInputView,
    URLInputView,
    WebsocketsURLValidator,
)
from elva.widgets.status import ComponentStatus, FeatureStatus, StatusBar
from elva.widgets.textarea import YTextArea

log = logging.getLogger(__name__)

LOG_LEVEL_MAP = dict(
    FATAL=logging.FATAL,
    ERROR=logging.ERROR,
    WARNING=logging.WARNING,
    INFO=logging.INFO,
    DEBUG=logging.DEBUG,
)
"""Mapping of logging levels to their corresponding names."""

LANGUAGES = {
    "py": "python",
    "md": "markdown",
    "sh": "bash",
    "js": "javascript",
    "rs": "rust",
    "yml": "yaml",
}
"""Supported languages."""


def get_provider(
    self, ydoc: Doc, **config: dict
) -> WebsocketProvider | ElvaWebsocketProvider:
    """
    Get the provider from the message parameter in the merged configuration.

    Arguments:
        ydoc: instance of a Y Document passed to the provider class.
        config: merged configuration parameters.

    Returns:
        instance of a provider.
    """
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


def encode_content(data: dict) -> str:
    """
    Encode data for inclusion in the displayed QR code for sharing.

    Currently, the data are written out in TOML syntax.

    Arguments:
        data: mapping to encode.

    Returns:
        data encoded in TOML syntax.
    """
    return tomli_w.dumps(data)


class LogStatus(FeatureStatus):
    """
    Widget reflecting the state of logging.
    """

    @property
    def is_ready(self) -> bool:
        """
        Flag whether all conditions for successful logging are fulfilled.

        Returns:
            `True` if all conditions are fulfilled, else `False`.
        """
        c = self.config
        path = c.get("path")
        return (
            path is not None
            and len(path.suffixes) > 0
            and not path.is_dir()
            and c.get("level") is not None
        )

    def apply(self):
        """
        Apply the new state.

        If [`is_ready`][elva.apps.editor.LogStatus.is_ready] returns `True`, logging gets reinitialized with updated parameters.
        Else, logging is stopped.
        """
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
            for handler in log.handlers[:]:
                log.removeHandler(handler)
            self.variant = "default"

    def on_button_pressed(self, message: Message):
        """
        Hook called on a button pressed event.

        Basically, this method toggles the state of the logging feature.

        Arguments:
            message: an object holding information about the button pressed event.
        """
        if self.variant == "success":
            for handler in log.handlers[:]:
                log.removeHandler(handler)
            self.variant = "default"
        else:
            self.apply()


class StoreStatus(ComponentStatus):
    """
    Widget reflecting the state of storage.
    """

    component = SQLiteStore
    """Instance of the controlled [`SQLiteStore`][elva.store.SQLiteStore] component."""

    @property
    def is_ready(self) -> bool:
        """
        Flag whether all conditions for successful storing are fulfilled.

        Returns:
            `True` if all conditions are fulfilled, else `False`.
        """
        c = self.config
        path = c.get("path")
        return (
            path is not None
            and len(path.suffixes) > 0
            and not path.is_dir()
            and c.get("identifier") is not None
        )

    def on_worker_state_changed(self, message: Message):
        """
        Hook called on a worker state change event.

        This method changes the status depending on the state of the worker the [`SQLiteStore`][elva.store.SQLiteStore] component is running in.

        Arguments:
            message: an object holding information about the worker state change event.
        """
        if message.worker.name == "component":
            match message.state:
                case WorkerState.RUNNING:
                    self.variant = "success"
                case WorkerState.ERROR:
                    self.variant = "error"
                    self.control = None
                case WorkerState.CANCELLED | WorkerState.SUCCESS:
                    self.variant = "default"
                    self.control = None


class RendererStatus(ComponentStatus):
    """
    Widget reflecting the state of rendering.
    """

    component = TextRenderer
    """Instance of the controlled [`TextRenderer`][elva.renderer.TextRenderer] component."""

    @property
    def is_ready(self) -> bool:
        """
        Flag whether all conditions for successful rendering are fulfilled.

        Returns:
            `True` if all conditions are fulfilled, else `False`.
        """
        path = self.config.get("path")
        return path is not None and len(path.suffixes) > 0 and not path.is_dir()

    def on_worker_state_changed(self, message: Message):
        """
        Hook called on a worker state change event.

        This method changes the status depending on the state of the worker the [`TextRenderer`][elva.renderer.TextRenderer] component is running in.

        Arguments:
            message: an object holding information about the worker state change event.
        """
        if message.worker.name == "component":
            match message.state:
                case WorkerState.RUNNING:
                    self.variant = "success"
                case WorkerState.ERROR:
                    self.variant = "error"
                    self.control = None
                case WorkerState.CANCELLED | WorkerState.SUCCESS:
                    self.variant = "default"
                    self.control = None


class ProviderStatus(ComponentStatus):
    """
    Widget reflecting the state of a provider.
    """

    component = get_provider
    """Instance of the controlled provider component."""

    @property
    def is_ready(self) -> bool:
        """
        Flag whether all conditions for successful connection are fulfilled.

        Returns:
            `True` if all conditions are fulfilled, else `False`.
        """
        c = self.config
        return c.get("identifier") and c.get("server")

    def on_worker_state_changed(self, message: Message):
        """
        Hook called on a worker state change event.

        This method changes the status depending on the state of the worker the provider component is running in.

        Arguments:
            message: an object holding information about the worker state change event.
        """
        if message.worker.name == "component":
            match message.state:
                case WorkerState.RUNNING:
                    self.variant = "warning"
                    self.run_worker(self.watch_connection_status(), group="event")
                case WorkerState.ERROR:
                    self.variant = "error"
                    self.control = None
                case WorkerState.CANCELLED | WorkerState.SUCCESS:
                    self.variant = "default"
                    self.control = None

    async def watch_connection_status(self):
        """
        Watch the connection status of the controlled provider component.

        This method listens for connection or disconnection events and update the status accordingly.
        """
        while True:
            await self.control.connected.wait()
            self.variant = "success"

            await self.control.disconnected.wait()
            self.variant = "warning"


class UI(App):
    """
    User interface.
    """

    CSS_PATH = "editor.tcss"
    """Path to the used textual CSS file."""

    BINDINGS = [Binding("ctrl+s", "save"), Binding("ctrl+r", "render")]
    """Key bindings for actions of the app."""

    def __init__(self, config: dict):
        """
        Arguments:
            config: mapping of configuration parameters to their values.
        """
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

    async def on_config_panel_applied(self, message: Message):
        """
        Hook called on an applied event from the config panel.

        This method transfers the new configuration to the status widgets.

        Arguments:
            message: an object holding information about the applied event.
        """
        for status_id in ["#provider", "#store", "#renderer", "#logger"]:
            self.query_one(status_id).update(message.config)

    async def on_exception(self, exc: Exception) -> Exception:
        """
        Hook called on an exception raised in the provider component.

        This method opens the config panel and updates the provider status widget to signal the issue to the user.

        Arguments:
            exc: the exception that the provide component raised.

        Raises:
            exc: the exception that was raised by the provider component.
        """
        if isinstance(exc, InvalidStatus) and exc.response.status_code == 401:
            self.query_one(ConfigPanel).remove_class("hidden")
            self.query_one("#provider").variant = "error"

        # reraise to break connection loop
        raise exc

    async def on_mount(self):
        """
        Hook called on mounting the app.
        """
        self.query_one(ConfigPanel).add_class("hidden")
        self.query_one(StoreStatus).disabled = True
        self.query_one(RendererStatus).disabled = True

    def compose(self):
        """
        Hook arranging child widgets.
        """
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
                    value=c.get("file"),
                    suggester=PathSuggester(),
                    name="file_path",
                ),
                PathInputView(
                    value=c.get("render"),
                    suggester=PathSuggester(),
                    name="render_path",
                ),
                SwitchView(
                    value=c.get("auto_render"),
                    name="auto_render",
                    animate=False,
                ),
                PathInputView(
                    value=c.get("log"),
                    suggester=PathSuggester(),
                    name="log",
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
                    "file",
                ],
                "S",
                config=self.config,
                rename={"file": "path"},
                id="store",
            )
            yield RendererStatus(
                self.ytext,
                [
                    "render",
                    "auto_render",
                ],
                "R",
                config=self.config,
                rename={"render": "path"},
                id="renderer",
            )
            yield LogStatus(
                [
                    "log",
                    "level",
                ],
                "L",
                config=self.config,
                rename={"log": "path"},
                id="logger",
            )

    def on_button_pressed(self, message: Message):
        """
        Hook called on a pressed button event.

        This methods toggles the visibility of the config panel.

        Arguments:
            message: an object holding information about the button pressed event.
        """
        button = message.button
        match button.id:
            case "config":
                self.query_one(ConfigPanel).toggle_class("hidden")

    def on_config_view_saved(self, message: Message):
        """
        Hook called on a Saved event from a config view.

        This methods saves the config view's key-value-pair as metadata entry to the ELVA SQLite database file.

        Arguments:
            message: an object holding information about the button pressed event.
        """
        c = self.query_one(ConfigPanel).state
        file_path = c.get("file")
        if file_path is not None and file_path.suffix and not file_path.is_dir():
            SQLiteStore.set_metadata(file_path, {message.name: message.value})

    def on_config_view_changed(self, message: Message):
        """
        Hook called on a [`Changed`][elva.widgets.config.ConfigView.Changed] event from a config view.

        This methods keeps the QR Code updated.

        Arguments:
            message: an object holding information about the button pressed event.
        """
        if message.name in ["identifier", "server", "messages"]:
            self.update_qrcode()

    def update_qrcode(self):
        """
        Update the QR code for sharing.

        This method queries the current values from the identifier, server and message views, encodes them and updates the QR Code with that.
        """
        identifier = self.query_one("#view-identifier").value
        server = self.query_one("#view-server").value
        messages = self.query_one("#view-messages").value

        content = encode_content(
            dict(identifier=identifier, server=server, messages=messages)
        )
        self.query_one("#view-share").value = content

    def action_render(self):
        """
        Hook called on an invoked render action.

        If a renderer component is running, its `write` method is called.
        Otherwise, the config panel opens to let the user fill in missing information.
        """
        renderer = self.query_one("#renderer").control
        if renderer is not None:
            self.run_worker(renderer.write())
        else:
            self.query_one(ConfigPanel).remove_class("hidden")

    def action_save(self):
        """
        Hook called on an invoked save action.

        If a store component is running, nothing happens - everything gets written automatically.
        Otherwise, the config panel opens to let the user fill in missing information.
        """
        store = self.query_one("#store").control
        if store is None:
            self.query_one(ConfigPanel).remove_class("hidden")

    @property
    def language(self) -> str:
        """
        The language the text document is written in.
        """
        c = self.config
        file_path = c.get("file")
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
    """
    Edit text documents collaboratively in real-time.
    \f

    Arguments:
        ctx: the click context holding the configuration parameter mapping.
        auto_render: flag whether to render on closing.
        apply: flag whether to mark the configuration as applied.
        ansi_color: flag whether to use the terminal's ANSI color codes.
        file: path to the ELVA SQLite database file.
    """

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
    log_path = c.get("log")
    level = c.get("level")
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
