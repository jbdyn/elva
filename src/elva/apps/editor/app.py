"""
ELVA editor app.
"""

import logging

from pycrdt import Doc, Text
from textual.app import App
from textual.binding import Binding

from elva.core import FILE_SUFFIX
from elva.provider import WebsocketProvider
from elva.renderer import TextRenderer
from elva.store import SQLiteStore
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

    BINDINGS = [Binding("ctrl+s", "save"), Binding("ctrl+r", "render")]
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
            )
            self.components.append(self.provider)

        if c.get("file") is not None:
            self.store = SQLiteStore(
                self.ydoc,
                c["identifier"],
                c["file"],
            )
            self.components.append(self.store)

            self.renderer = TextRenderer(
                self.ytext,
                c["render"],
                c.get("auto_save", False),
                c.get("timeout", 300),
            )
            self.components.append(self.renderer)

        self._language = c.get("language")

    async def wait_for_component_state(self, component, state):
        sub = component.subscribe()
        while state != component.state:
            await sub.receive()
        component.unsubscribe(sub)

    async def on_mount(self):
        """
        Hook called on mounting the app.
        """
        for comp in self.components:
            self.run_worker(comp.start())
            await self.wait_for_component_state(
                comp, comp.states.ACTIVE | comp.states.RUNNING
            )

    async def on_unmount(self):
        """
        Hook called on unmounting the app.
        """
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

    async def action_render(self):
        """
        Action performed on triggering the `render` key binding.
        """
        if hasattr(self, "renderer"):
            await self.renderer.write()
