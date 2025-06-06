import asyncio

from pycrdt import Doc
from pycrdt_websocket import WebsocketProvider
from websockets import connect


def callback(event):
    print("changes observed")
    print(event.update)


async def client():
    ydoc = Doc()
    async with (
        connect("ws://localhost:1234/my-roomname") as websocket,
        WebsocketProvider(ydoc, websocket),
    ):
        # Changes to remote ydoc are applied to local ydoc.
        # Changes to local ydoc are sent over the WebSocket and
        # broadcast to all clients.

        ydoc.observe(callback)

        await asyncio.Future()  # run forever


asyncio.run(client())
