import anyio

from elva.component import Component

class TextRenderer(Component):
    def __init__(self, ytext, path):
        self.ytext = ytext
        self.path = anyio.Path(path)

    async def cleanup(self):
        await self.write()

    async def write(self):
        async with await anyio.open_file(self.path, "w") as file:
            await file.write(str(self.ytext))

