"""
ELVA editor app.
"""

import logging
from pathlib import Path

from pycrdt import Doc, Text
from textual.app import App
from textual.binding import Binding
from websockets.exceptions import InvalidStatus

from elva.cli import get_data_file_path, get_render_file_path
from elva.core import FILE_SUFFIX
from elva.provider import WebsocketProvider
from elva.renderer import TextRenderer
from elva.store import SQLiteStore
from elva.widgets.awareness import AwarenessView
from elva.widgets.config import ConfigView
from elva.widgets.screens import Dashboard, ErrorScreen, InputScreen
from elva.widgets.ytextarea import YTextArea

log = logging.getLogger(__package__)

LANGUAGES = {
    "py": "python",
    "md": "markdown",
    "sh": "bash",
    "js": "javascript",
    "rs": "rust",
    "yml": "yaml",
}
"""Supported languages."""


class UI(App):
    """
    User interface.
    """

    CSS_PATH = "style.tcss"
    """The path to the default CSS."""

    SCREENS = {
        "dashboard": Dashboard,
        "input": InputScreen,
    }

    BINDINGS = [
        Binding("ctrl+s", "save"),
        Binding("ctrl+r", "render"),
        Binding("ctrl+b", "toggle_dashboard"),
    ]
    """Key bindings for actions of the app."""

    def __init__(self, config: dict):
        """
        Arguments:
            config: mapping of configuration parameters to their values.
        """
        self.config = c = config

        ansi_color = c.get("ansi_color", False)
        super().__init__(ansi_color=ansi_color)

        # document structure
        self.ydoc = Doc()
        self.ytext = Text()
        self.ydoc["ytext"] = self.ytext

        self.components = list()

        if c.get("host") is not None:
            self.provider = WebsocketProvider(
                self.ydoc,
                c["identifier"],
                c["host"],
                port=c.get("port"),
                safe=c.get("safe", True),
                on_exception=self.on_provider_exception,
            )

            data = {}
            if c.get("name") is not None:
                data = {"user": {"name": c["name"]}}

            self.provider.awareness.set_local_state(data)

            self.components.append(self.provider)

        if c.get("file") is not None:
            self.store = SQLiteStore(
                self.ydoc,
                c["identifier"],
                c["file"],
            )
            self.components.append(self.store)

        if c.get("render") is not None:
            self.renderer = TextRenderer(
                self.ytext,
                c["render"],
                c.get("auto_save", False),
                c.get("timeout", 300),
            )
            self.components.append(self.renderer)

        self._language = c.get("language")

    def on_provider_exception(self, exc, config):
        self.run_worker(self._on_provider_exception(exc, config))

    async def _on_provider_exception(self, exc, config):
        await self.provider.stop()

        if type(exc) is InvalidStatus:
            response = exc.response
            exc = f"HTTP {response.status_code}: {response.reason_phrase}"

        await self.push_screen_wait(ErrorScreen(exc))
        self.exit(return_code=1)

    def on_awareness_update(self, topic, data):
        if topic == "change":
            self.run_worker(self._on_awareness_update(topic, data))

    async def _on_awareness_update(self, topic, data):
        if self.screen == self.get_screen("dashboard"):
            self.push_client_states()

    async def wait_for_component_state(self, component, state):
        sub = component.subscribe()
        while state != component.state:
            await sub.receive()
        component.unsubscribe(sub)

    async def on_mount(self):
        """
        Hook called on mounting the app.
        """
        if hasattr(self, "provider"):
            self.subscription = self.provider.awareness.observe(
                self.on_awareness_update
            )

        # load text from rendered file
        c = self.config

        text = ""

        render_file_path = c.get("render")
        if render_file_path is not None and render_file_path.exists():
            # we found some content on disk;
            # now check whether this has precedence over the data file
            data_file_path = c.get("file")
            if data_file_path is None or not data_file_path.exists():
                # there is no data file on disk associated with this
                # file name; we load the content
                with render_file_path.open(mode="r") as fd:
                    text = fd.read()

        # wait for components to run
        for comp in self.components:
            self.run_worker(comp.start())
            await self.wait_for_component_state(
                comp, comp.states.ACTIVE | comp.states.RUNNING
            )

        # now add the text to save updates to disk and send them over wire
        if text:
            ytextarea = self.query_one(YTextArea)
            ytextarea.load_text(text)

    async def on_unmount(self):
        """
        Hook called on unmounting the app.
        """
        if hasattr(self, "subscription"):
            self.provider.awareness.unobserve(self.subscription)
            del self.subscription

        for comp in self.components:
            await self.wait_for_component_state(comp, comp.states.NONE)

    def compose(self):
        """
        Hook arranging child widgets.
        """
        yield YTextArea(
            self.ytext,
            tab_behavior="indent",
            show_line_numbers=True,
            id="editor",
            language=self.language,
        )

    @property
    def language(self) -> str:
        """
        The language the text document is written in.
        """
        c = self.config
        file_path = c.get("file")
        if file_path is not None and file_path.suffix:
            suffixes = "".join(file_path.suffixes)
            suffix = suffixes.split(FILE_SUFFIX)[0].removeprefix(".")
            if str(file_path).endswith(suffix):
                log.info("continuing without syntax highlighting")
            else:
                try:
                    language = LANGUAGES[suffix]
                    log.info(f"enabled {language} syntax highlighting")
                    return language
                except KeyError:
                    log.info(
                        f"no syntax highlighting available for file type '{suffix}'"
                    )
        else:
            return self._language

    async def action_save(self):
        if self.config.get("file") is None:
            self.run_worker(self.get_and_set_file_paths())

    async def get_and_set_file_paths(self, data_file=True):
        name = await self.push_screen_wait("input")

        if not name:
            return

        path = Path(name)

        data_file_path = get_data_file_path(path)
        if data_file:
            self.config["file"] = data_file_path
            self.store = SQLiteStore(
                self.ydoc, self.config["identifier"], data_file_path
            )
            self.components.append(self.store)
            self.run_worker(self.store.start())

        if self.config.get("render") is None:
            render_file_path = get_render_file_path(data_file_path)
            self.config["render"] = render_file_path

            self.renderer = TextRenderer(
                self.ytext, render_file_path, self.config.get("auto_save", False)
            )
            self.components.append(self.renderer)
            self.run_worker(self.renderer.start())

        if self.screen == self.get_screen("dashboard"):
            self.push_config()

    async def action_render(self):
        """
        Action performed on triggering the `render` key binding.
        """
        if self.config.get("render") is None:
            self.run_worker(self.get_and_set_file_paths(data_file=False))
        else:
            await self.renderer.write()

    async def action_toggle_dashboard(self):
        if self.screen == self.get_screen("dashboard"):
            self.pop_screen()
        else:
            await self.push_screen("dashboard")
            self.push_client_states()
            self.push_config()

    def push_client_states(self):
        if hasattr(self, "provider"):
            client_states = self.provider.awareness.client_states.copy()
            client_id = self.provider.awareness.client_id
            if client_id not in client_states:
                return
            states = list()
            states.append((client_id, client_states.pop(client_id)))
            states.extend(list(client_states.items()))
            states = tuple(states)

            awareness_view = self.screen.query_one(AwarenessView)
            awareness_view.states = states

    def push_config(self):
        config = tuple(self.config.items())

        config_view = self.screen.query_one(ConfigView)
        config_view.config = config
