import io
import logging
from pathlib import Path

import anyio
import click
import qrcode
import tomli_w
import websockets.exceptions as wsexc
from pycrdt import Doc, Text
from pyperclip import copy as copy_to_clipboard
from rich.text import Text as RichText
from textual.app import App
from textual.binding import Binding
from textual.containers import Container, Grid, Horizontal, VerticalScroll
from textual.message import Message
from textual.suggester import Suggester
from textual.validation import Validator
from textual.widget import Widget
from textual.widgets import (
    Button,
    Collapsible,
    Input,
    Label,
    RadioButton,
    RadioSet,
    Static,
    Switch,
)
from websockets import parse_uri

from elva.auth import basic_authorization_header
from elva.log import LOGGER_NAME, DefaultFormatter
from elva.provider import ElvaWebsocketProvider, WebsocketProvider
from elva.renderer import TextRenderer
from elva.store import SQLiteStore
from elva.utils import FILE_SUFFIX, gather_context_information
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


def generate_qrcode(qr, data):
    content = tomli_w.dumps(data)
    qr.clear()
    qr.add_data(content)
    f = io.StringIO()
    qr.print_ascii(out=f)
    f.seek(0)
    return f.read()


class QRCodeLabel(Widget):
    def __init__(self, content):
        super().__init__()
        self.label = Static(content, id="qrcode")

    def compose(self):
        with Collapsible(title="QR"):
            yield self.label

    @property
    def value(self):
        return self.label.renderable

    @value.setter
    def value(self, new):
        self.label.update(new)


class Status(Label):
    @property
    def state(self):
        return self.classes

    @state.setter
    def state(self, new):
        self.set_classes(new)


class StatusBar(Container):
    def compose(self):
        with Grid():
            yield Button("=", id="config")
            yield Status("P", id="provider")
            yield Status("S", id="store")
            yield Status("R", id="renderer")
            yield Status("L", id="logger")


class RadioSelect(Container):
    def __init__(self, options, *args, value=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.names, self.values = list(zip(*options))
        if value is None:
            value = self.values[0]
        elif value not in self.values:
            raise AttributeError(f"value '{value}' is not in values {self.values}")

        self.buttons = dict(
            (n, RadioButton(n, value=(v == value), name=n)) for n, v in options
        )
        self.options = dict(options)

        self.radio_set = RadioSet()

    @classmethod
    def from_values(cls, options, *args, value=None, **kwargs):
        options = [(str(option), option) for option in options]

        return cls(options, *args, value=value, **kwargs)

    def compose(self):
        with self.radio_set:
            for button in self.buttons.values():
                yield button

    @property
    def value(self):
        return self.options[self.radio_set.pressed_button.name]

    @value.setter
    def value(self, new):
        name = self.names[self.values.index(new)]
        self.buttons[name].value = True

    def on_click(self, message):
        self.radio_set.pressed_button.focus()


class ConfigPanel(Container):
    class ConfigSaved(Message):
        def __init__(self, last, config, changed):
            super().__init__()
            self.last = last
            self.config = config
            self.changed = changed

    def __init__(self, config, applied=False):
        super().__init__()
        self.config = config
        self.applied = applied

    @property
    def state(self):
        return dict((c.name, c.value) for c in self.config)

    @property
    def last(self):
        return dict((c.name, c.last) for c in self.config)

    @property
    def changed(self):
        if self.applied:
            return set(c.name for c in self.config if c.changed)
        else:
            return set(c.name for c in self.config)

    def compose(self):
        with Grid():
            with VerticalScroll():
                for c in self.config:
                    c.border_title = c.name
                    yield c
            with Grid():
                yield Button("Apply", id="apply")
                yield Button("Reset", id="reset")

    def apply(self):
        for c in self.config:
            c.apply()
        self.applied = True

    def reset(self):
        for c in self.config:
            c.reset()

    def post_changed_config(self):
        self.post_message(self.ConfigSaved(self.last, self.state, self.changed))
        self.apply()

    def on_input_submitted(self, message):
        self.post_changed_config()

    def on_button_pressed(self, message):
        match message.button.id:
            case "apply":
                self.post_changed_config()
            case "reset":
                self.reset()


class ConfigView(Widget):
    class Changed(Message):
        def __init__(self, name, value):
            super().__init__()
            self.name = name
            self.value = value

    class Saved(Message):
        def __init__(self, name, value):
            super().__init__()
            self.name = name
            self.value = value

    def __init__(self, widget):
        super().__init__()
        self.widget = widget

    def compose(self):
        yield self.widget

    def on_mount(self):
        self.apply()

    def apply(self):
        self.last = self.value

    def reset(self):
        self.value = self.last

    @property
    def changed(self):
        return self.last != self.value

    @property
    def name(self):
        return self.widget.name

    @property
    def value(self):
        return self.widget.value

    @value.setter
    def value(self, new):
        self.widget.value = new

    def on_click(self, message):
        self.widget.focus()


class RadioSelectView(ConfigView):
    def __init__(self, *args, **kwargs):
        widget = RadioSelect(*args, **kwargs)
        super().__init__(widget)

    def compose(self):
        with Grid():
            yield self.widget
            yield Button("S", id=f"save-{self.name}")

    def on_button_pressed(self, message):
        self.post_message(self.Saved(self.name, self.value))

    def on_click(self, message):
        self.widget.radio_set.focus()

    def on_radio_set_changed(self, message):
        self.post_message(self.Changed(self.name, self.value))


class TextInputView(ConfigView):
    def __init__(self, *args, **kwargs):
        widget = Input(*args, **kwargs)
        super().__init__(widget)

    def compose(self):
        with Grid():
            yield self.widget
            yield Button("X", id=f"clear-{self.name}")
            yield Button("C", id=f"copy-{self.name}")
            yield Button("S", id=f"save-{self.name}")

    def on_button_pressed(self, message):
        button_id = message.button.id
        clear_id = f"clear-{self.name}"
        copy_id = f"copy-{self.name}"
        save_id = f"save-{self.name}"

        if button_id == clear_id:
            self.widget.clear()
        elif button_id == copy_id:
            copy_to_clipboard(self.value)
        elif button_id == save_id:
            self.post_message(self.Saved(self.name, self.value))

    def on_input_changed(self, message):
        self.post_message(self.Changed(self.name, self.value))


class URLInputView(TextInputView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_valid = True

    def on_input_changed(self, message):
        validation_result = message.validation_result
        if validation_result is not None:
            if validation_result.is_valid:
                self.is_valid = True
                self.remove_class("invalid")
                self.post_message(self.Changed(self.name, self.value))
            else:
                self.is_valid = False
                self.add_class("invalid")

    @property
    def value(self):
        return self.widget.value if self.is_valid else None

    @value.setter
    def value(self, new):
        self.widget.value = new


class PathInputView(TextInputView):
    @property
    def value(self):
        entry = self.widget.value
        return Path(entry) if entry else None

    @value.setter
    def value(self, new):
        self.widget.value = str(new) if new is not None else ""


class SwitchView(ConfigView):
    def __init__(self, *args, **kwargs):
        widget = Switch(*args, **kwargs)
        super().__init__(widget)

    def compose(self):
        with Grid():
            with Container():
                yield self.widget
            yield Button("S", id=f"save-{self.name}")

    def on_button_pressed(self, message):
        self.post_message(self.Saved(self.name, self.value))


class WebsocketsURLValidator(Validator):
    def validate(self, value):
        if value:
            try:
                parse_uri(value)
            except Exception as exc:
                return self.failure(description=str(exc))
            else:
                return self.success()
        else:
            return self.success()


class PathSuggester(Suggester):
    async def get_suggestion(self, value):
        path = Path(value)

        if path.is_dir():
            dir = path
        else:
            dir = path.parent

        try:
            _, dirs, files = next(dir.walk())
        except StopIteration:
            return value

        names = sorted(dirs) + sorted(files)
        try:
            name = next(filter(lambda n: n.startswith(path.name), names))
        except StopIteration:
            if path.is_dir():
                name = names[0] if names else ""
            else:
                name = path.name

        if value.startswith("."):
            prefix = "./"
        else:
            prefix = ""

        return prefix + str(dir / name)


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
        name: str | None = None,
        user: str | None = None,
        password: str | None = None,
        auto_render: bool = False,
        log_path: None | Path = None,
        level: None | int = None,
    ):
        super().__init__(ansi_color=True)

        self.messages = messages
        self.qr = qrcode.QRCode(border=0)

        qr_label = (
            generate_qrcode(
                self.qr, dict(identifier=identifier, server=server, messages=messages)
            )
            if identifier is not None and server is not None and messages is not None
            else None
        )

        # ConfigPanel widgets
        self.config_widgets = [
            ConfigView(QRCodeLabel(qr_label)),
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
                value=name,
                name="name",
            ),
            TextInputView(
                value=user,
                name="user",
            ),
            TextInputView(
                value=password,
                name="password",
                password=True,
            ),
            PathInputView(
                value=str(file_path) if file_path is not None else None,
                # suggester=PathSuggester(),
                name="file_path",
            ),
            PathInputView(
                value=str(render_path) if render_path is not None else None,
                # suggester=PathSuggester(),
                name="render_path",
            ),
            SwitchView(
                value=auto_render,
                name="auto_render",
                animate=False,
            ),
            PathInputView(
                value=str(log_path) if log_path is not None else None,
                # suggester=PathSuggester(),
                name="log_path",
            ),
            RadioSelectView(
                list(LOG_LEVEL_MAP.items()),
                value=level,
                name="level",
            ),
        ]

        self.config_panel = ConfigPanel(self.config_widgets)

        self.store_config = set(["identifier", "file_path"])
        self.provider_config = set(
            ["identifier", "server", "messages", "user", "password"]
        )
        self.renderer_config = set(["render_path", "auto_render"])
        self.log_config = set(["log_path"])

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
    async def on_config_panel_config_saved(self, message):
        changed = message.changed
        config = message.config

        log.setLevel(config["level"])

        if not changed.isdisjoint(self.log_config):
            log_path = config["log_path"]

            for handler in log.handlers[:]:
                log.removeHandler(handler)

            status_label = self.query_one("#logger", Status)

            if log_path is not None and log_path.suffixes and not log_path.is_dir():
                handler = logging.FileHandler(log_path)
                handler.setFormatter(DefaultFormatter())
                log.addHandler(handler)
                status_label.state = "success"
            else:
                status_label.state = ""

        if not changed.isdisjoint(self.store_config):
            store_config = dict((key, config[key]) for key in self.store_config)
            path = store_config.pop("file_path")

            status_label = self.query_one("#store", Status)

            if path.suffixes and not path.is_dir() and store_config["identifier"]:
                store_config["path"] = path
                store = SQLiteStore(self.ydoc, **store_config)
                self.run_worker(
                    store.start(),
                    group="store",
                    exclusive=True,
                )
                await store.started.wait()
                status_label.state = "success"
            else:
                self.workers.cancel_group(self, "store")
                status_label.state = ""

        if not changed.isdisjoint(self.renderer_config):
            renderer_config = dict((key, config[key]) for key in self.renderer_config)
            path = renderer_config.pop("render_path")
            renderer_config["path"] = path
            status_label = self.query_one("#renderer", Status)

            if path.suffix and not path.is_dir():
                renderer = TextRenderer(self.ytext, **renderer_config)
                self.run_worker(
                    renderer.start(),
                    group="renderer",
                    exclusive=True,
                )
                await renderer.started.wait()
                status_label.state = "success"
            else:
                self.workers.cancel_group(self, "renderer")
                status_label.state = ""

        if not changed.isdisjoint(self.provider_config):
            provider_config = dict((key, config[key]) for key in self.provider_config)
            self.messages = provider_config.pop("messages")
            Provider = self.get_provider()

            user = provider_config.pop("user")
            password = provider_config.pop("password")
            if user:
                self.basic_authorization_header = basic_authorization_header(
                    user, password
                )
            else:
                self.basic_authorization_header = None

            status_label = self.query_one("#provider", Status)

            if provider_config["identifier"] and provider_config["server"]:
                provider = Provider(self.ydoc, **provider_config)
                self.run_worker(
                    provider.start(),
                    group="provider",
                    exclusive=True,
                )
                await provider.started.wait()
                status_label.state = "success"
            else:
                self.workers.cancel_group(self, "provider")
                status_label.state = ""

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
        self.config_panel.add_class("hidden")
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
        # async with anyio.create_task_group() as tg:
        #    for component in self.components.values():
        #        tg.start_soon(component.stopped.wait)
        await self.workers.wait_for_complete()

    def compose(self):
        yield self.ytext_area
        yield self.config_panel
        yield StatusBar()

    def on_button_pressed(self, message):
        button = message.button
        if button.id == "config":
            self.config_panel.toggle_class("hidden")

    def on_config_view_saved(self, message):
        config = self.config_panel.state
        file_path = config["file_path"]
        if file_path.is_file():
            SQLiteStore.set_metadata(file_path, {message.name: message.value})

    def on_config_view_changed(self, message):
        if message.name in ["identifier", "server", "messages"]:
            qr_label = self.query_one("#qrcode")

            identifier = self.query_one("#view-identifier").value
            server = self.query_one("#view-server").value
            messages = self.query_one("#view-messages").value

            qr_label.update(
                generate_qrcode(
                    self.qr,
                    dict(identifier=identifier, server=server, messages=messages),
                )
            )

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
    "--auto-render",
    "auto_render",
    is_flag=True,
    help="Enable rendering of the data file.",
)
@click.argument(
    "file",
    required=False,
    type=click.Path(path_type=Path, dir_okay=False),
)
@click.pass_context
def cli(ctx: click.Context, auto_render: bool, file: None | Path):
    """Edit text documents collaboratively in real-time."""

    c = ctx.obj

    # gather info
    gather_context_information(ctx, file=file, app="editor")

    if auto_render:
        # the flag has been explicitly set by the user
        c["auto_render"] = auto_render

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
        c["name"],
        c["user"],
        c["password"],
        c["auto_render"],
        log_path,
        level,
    )
    ui.run()


if __name__ == "__main__":
    cli()
