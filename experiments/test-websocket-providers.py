from elva.provider import WebsocketElvaProvider
from pycrdt import Doc, Text
from pycrdt_websocket import WebsocketProvider
from time import sleep
import anyio
import elva.logging_config
import logging
import sys
import websockets

log = logging.getLogger(__name__)

def callback(event):
    print(event.target)

async def add_text(text, chars):
    while True:
        text += chars
        await anyio.sleep(1)

async def connection_status(provider):
    await provider.started.wait()
    print("connected!")

async def main(chars):
    ydoc = Doc()
    text = Text()
    ydoc["text"] = text
    text.observe(callback)

    async with WebsocketElvaProvider({None: ydoc}, "ws://localhost:8000/test") as provider:
#    async with websockets.connect("ws://localhost:8000/test") as ws, WebsocketProvider(ydoc, ws) as provider:
        async with anyio.create_task_group() as tg:
            tg.start_soon(add_text, text, chars)
            tg.start_soon(connection_status, provider)
            
anyio.run(main, sys.argv[1])
