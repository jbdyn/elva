import asyncio
from pycrdt import Doc
from jupyter_ydoc import YBlob
from websockets import connect
from pycrdt_websocket import WebsocketProvider

async def client():
    ydoc = Doc()
    async with (
        connect("ws://localhost:1234/my-roomname") as websocket,
        WebsocketProvider(ydoc, websocket),
    ):
        # Changes to remote ydoc are applied to local ydoc.
        # Changes to local ydoc are sent over the WebSocket and
        # broadcast to all clients.
        
        with open('Rundschreiben.pdf', 'rb') as file:
            blob = YBlob(ydoc)
            print("setting yblob")
            blob.set(file.read())

        await asyncio.Future()  # run forever

asyncio.run(client())
