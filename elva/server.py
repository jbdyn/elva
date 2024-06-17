import asyncio
from websockets import serve
from pycrdt_websocket import WebsocketServer
import logging

log = logging.basicConfig()

async def server():
    async with (
        WebsocketServer(log=log) as websocket_server,
        serve(websocket_server.serve, "localhost", 8000),
    ):
        await asyncio.Future()  # run forever

asyncio.run(server())
