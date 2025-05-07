"""
Module holding renderer components.
"""

import anyio
from pycrdt import Text

from elva.component import Component


class TextRenderer(Component):
    """
    Component rendering Y text data types to text files.
    """

    ytext: Text
    """Instance of a Y text data type."""

    path: anyio.Path
    """Path where to store the rendered text file."""

    auto_render: bool
    """Flag whether to render to text file on hook execution."""

    def __init__(self, ytext: Text, path: str, auto_render: bool = True):
        """
        Arguments:
            ytext: instance of a Y text data type.
        """
        self.ytext = ytext
        self.path = anyio.Path(path)
        self.auto_render = auto_render

    async def run(self):
        """
        Hook after the component has been started.

        The contents of `self.ytext` get rendered to file if [`auto_render`][elva.renderer.TextRenderer.auto_render] is `True`.
        """
        if self.auto_render:
            await self.write()

    async def cleanup(self):
        """
        Hook after the component has been cancelled.

        The contents of `self.ytext` get rendered to file if [`auto_render`][elva.renderer.TextRenderer.auto_render] is `True`.
        """
        if self.auto_render:
            await self.write()
            self.log.info(f"saved and closed file {self.path}")

    async def write(self):
        """
        Render the contents of [`ytext`][elva.renderer.TextRenderer.ytext] to file.
        """
        async with await anyio.open_file(self.path, "w") as self.file:
            self.log.info(f"writing to file {self.path}")
            await self.file.write(str(self.ytext))
