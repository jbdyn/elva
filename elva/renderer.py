import anyio

from elva.base import Component

class TextRenderer(Component):
    def __init__(self, ytext, path):
        self.ytext = ytext
        self.path = anyio.Path(path)

    async def cleanup(self):
        await self.write()

    async def write(self):
        mode = "r+" if await self.path.exists() else "w"
        async with await anyio.open_file(self.path, mode) as file:
            await file.write(str(self.ytext))

