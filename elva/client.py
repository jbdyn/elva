import asyncio
from pycrdt import Doc
from jupyter_ydoc import YBlob
from websockets import connect
from pycrdt_websocket import WebsocketProvider
from tree import ElvaTree

import sys

async def client(path):
    doc = Doc()
    tree = ElvaTree(path=path, doc=doc)
    async with (
        connect("ws://localhost:1234/my-roomname") as websocket,
        WebsocketProvider(doc, websocket),
    ):
        # Changes to remote ydoc are applied to local ydoc.
        # Changes to local ydoc are sent over the WebSocket and
        # broadcast to all clients.
        
        #with open('Rundschreiben.pdf', 'rb') as file:
        #    blob = YBlob(ydoc)
        #    print("setting yblob")
        #    blob.set(file.read())
        await tree.start()
        await asyncio.Future()  # run forever

asyncio.run(client(sys.argv[1]))
