import asyncio
import logging

from websockets import serve

import elva.log
from elva.pycrdt_websocket_server import WebsocketServer

log = logging.getLogger("elva.pycrdt_websocket_server")

async def server():
    async with (
        WebsocketServer(log=log) as websocket_server,
        serve(websocket_server.serve, "localhost", 8000),
    ):
        await asyncio.Future()  # run forever

asyncio.run(server())
