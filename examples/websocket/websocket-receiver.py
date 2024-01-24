import anyio
from anyio.streams.file import FileWriteStream
import asyncio
import websockets
import datetime
import sys
import random
import os

async def send(socket):
    msg = sys.argv[1]
    print(">", msg)
    await socket.send(msg)
    await receive(socket)

async def receive(socket):
    async for item in socket:
        print("<", item)
        #print(os.path.exists(item))
        #if os.path.exists(item):
        #    print("opening new websocket")
         #   async with websockets.connect("ws://localhost:8000/" + item) as file_socket:
         #       async with await FileReadStream.from_path(item) as frstream:
         #           async for chunk in frstream:
         #               await socket.send(chunk)

async def main():
    async with (
        websockets.connect("ws://localhost:8000/" + sys.argv[1]) as websocket,
    ):
        async with anyio.create_task_group() as tg:
            #tg.start_soon(send, websocket)
            tg.start_soon(receive, websocket)

anyio.run(main)
