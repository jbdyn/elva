import logging
from pathlib import Path

import anyio
import click
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
from textual.widgets import Button, Input, Label, RadioButton, RadioSet, Static, Switch
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

LANGUAGES = {
    "py": "python",
    "md": "markdown",
    "sh": "bash",
    "js": "javascript",
    "rs": "rust",
    "yml": "yaml",
}


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
            yield Button("P", id="provider")
            yield Button("S", id="store")
            yield Button("R", id="renderer")
            yield Button("L", id="logger")
            yield Button("=", id="config")


class RadioSelect(Container):
    def __init__(self, options, *args, value=None, **kwargs):
        super().__init__(*args, **kwargs)
        if value is None:
            value = options[0]
        self.options = options
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

    def on_click(self, message):
        self.widget.radio_set.focus()


class TextInputView(ConfigView):
    def __init__(self, *args, **kwargs):
        widget = Input(*args, **kwargs)
        super().__init__(widget)

    def compose(self):
        with Grid():
            yield self.widget
            yield Button("X", id=f"clear-{self.name}")
            yield Button("C", id=f"copy-{self.name}")

    def on_button_pressed(self, message):
        button_id = message.button.id
        clear_id = f"clear-{self.name}"
        copy_id = f"copy-{self.name}"

        if button_id == clear_id:
            self.widget.clear()
        elif button_id == copy_id:
            copy_to_clipboard(self.value)


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
            else:
                self.is_valid = False
                self.add_class("invalid")

    @property
    def value(self):
        return self.widget.value if self.is_valid else ""

    @value.setter
    def value(self, new):
        self.widget.value = new


class PathInputView(TextInputView):
    @property
    def value(self):
        return Path(self.widget.value)

    @value.setter
    def value(self, new):
        self.widget.value = str(new)


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
        user: str | None = None,
        password: str | None = None,
        auto_render: bool = False,
        log_path: None | Path = None,
        level=None,
    ):
        super().__init__(ansi_color=True)

        self.messages = messages

        # ConfigPanel widgets
        self.config_widgets = [
            TextInputView(
                value=identifier,
                name="identifier",
            ),
            URLInputView(
                value=server,
                name="server",
                validators=WebsocketsURLValidator(),
                validate_on=["changed"],
            ),
            RadioSelectView(
                ["yjs", "elva"],
                value=messages,
                name="messages",
            ),
            TextInputView(value=user, name="user"),
            TextInputView(
                value=password,
                name="password",
                password=True,
            ),
            PathInputView(
                value=str(file_path) if file_path is not None else "",
                # suggester=PathSuggester(),
                name="file_path",
            ),
            PathInputView(
                value=str(render_path) if render_path is not None else "",
                # suggester=PathSuggester(),
                name="render_path",
            ),
            ConfigView(
                Switch(
                    value=auto_render,
                    name="auto_render",
                    animate=False,
                )
            ),
            PathInputView(
                value=str(log_path) if log_path is not None else "",
                # suggester=PathSuggester(),
                name="log_path",
            ),
            RadioSelectView(
                list(logging.getLevelNamesMapping().keys()),
                value=logging.getLevelName(level) if level is not None else "INFO",
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

        log.setLevel(logging.getLevelNamesMapping()[config["level"]])

        if not changed.isdisjoint(self.log_config):
            log_path = config["log_path"]

            for handler in log.handlers[:]:
                log.removeHandler(handler)

            if log_path.suffixes:
                handler = logging.FileHandler(log_path)
                handler.setFormatter(DefaultFormatter())
                log.addHandler(handler)

        if not changed.isdisjoint(self.store_config):
            store_config = dict((key, config[key]) for key in self.store_config)
            path = store_config.pop("file_path")

            if path.suffixes and store_config["identifier"]:
                store_config["path"] = path
                store = SQLiteStore(self.ydoc, **store_config)
                self.run_worker(
                    store.start(),
                    group="store",
                    exclusive=True,
                )
                await store.started.wait()
            else:
                self.workers.cancel_group(self, "store")

        if not changed.isdisjoint(self.renderer_config):
            renderer_config = dict((key, config[key]) for key in self.renderer_config)
            path = renderer_config.pop("render_path")
            renderer_config["path"] = path
            if path.suffix:
                renderer = TextRenderer(self.ytext, **renderer_config)
                self.run_worker(
                    renderer.start(),
                    group="renderer",
                    exclusive=True,
                )
                await renderer.started.wait()
            else:
                self.workers.cancel_group(self, "renderer")

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

            if provider_config["identifier"] and provider_config["server"]:
                provider = Provider(self.ydoc, **provider_config)
                self.run_worker(
                    provider.start(),
                    group="provider",
                    exclusive=True,
                )
                await provider.started.wait()
            else:
                self.workers.cancel_group(self, "provider")

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
        yield StatusBar()
        with Horizontal():
            yield self.ytext_area
            yield self.config_panel

    def on_button_pressed(self, message):
        button = message.button
        if button.id == "config":
            self.config_panel.toggle_class("hidden")

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
        log_path,
        level,
    )
    ui.run()


if __name__ == "__main__":
    cli()
