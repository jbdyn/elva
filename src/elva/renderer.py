import anyio

from elva.component import Component


class TextRenderer(Component):
    def __init__(self, ytext, path, auto_render=True):
        self.ytext = ytext
        self.path = anyio.Path(path)
        self.auto_render = auto_render

    async def run(self):
        if self.auto_render:
            await self.write()

    async def cleanup(self):
        if self.auto_render:
            await self.write()
            self.log.info(f"saved and closed file {self.path}")

    async def write(self):
        async with await anyio.open_file(self.path, "w") as self.file:
            self.log.info(f"writing to file {self.path}")
            await self.file.write(str(self.ytext))
