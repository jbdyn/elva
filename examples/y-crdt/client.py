import asyncio
import y_py as Y
from websockets import connect
from ypy_websocket import WebsocketProvider
import sys
from functools import partial

def callback(event):
    target = event.target
    print(target.to_json())

async def client(name):
    ydoc = Y.YDoc()
    async with (
        connect("ws://localhost:1234/my-roomname") as websocket,
        WebsocketProvider(ydoc, websocket) as provider,
    ):
        # Changes to remote ydoc are applied to local ydoc.
        # Changes to local ydoc are sent over the WebSocket and
        # broadcast to all clients.
        ymap = ydoc.get_map("map")
        ymap.observe(callback)
        if name == "Ernie":
            sleep = 2.3
        else:
            sleep = 7.8
        i = 0
        while True:
            with ydoc.begin_transaction() as t:
                ymap.set(t, name, str(i))
            await asyncio.sleep(sleep)
            i += 1

        await asyncio.Future()  # run forever

name = sys.argv[1]
asyncio.run(client(name))
