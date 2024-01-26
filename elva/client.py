import anyio
from pycrdt import Doc, Text
from pycrdt_websocket import WebsocketProvider
from websockets import connect
from apps.editor import Editor
from providers import ElvaProvider
from time import sleep


async def client():
    ydoc = Doc()
    editor = Editor(ydoc)
    uuid = "9914bba9-8f17-429f-ab97-6b60f61bc49"
    async with (
        connect("ws://localhost:1234/") as websocket,
        ElvaProvider({uuid: ydoc}, websocket) as provider,
    ):
        await editor.run_async()

anyio.run(client)
