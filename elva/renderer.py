import anyio

from elva.component import Component

class TextRenderer(Component):
    def __init__(self, ytext, path):
        self.ytext = ytext
        self.modified = False
        self.path = anyio.Path(path)

    async def before(self):
        mode = "r+" if await self.path.exists() else "w"
        self.file = await anyio.open_file(self.path, mode)

    async def cleanup(self):
        await self.write()
        await self.file.aclose()

    async def write(self):
        if self.modified:
            await self.file.truncate(0)
            await self.file.seek(0)
            await self.file.write(str(self.ytext))
            self.modified = False

