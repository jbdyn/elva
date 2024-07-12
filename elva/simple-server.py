#!/usr/bin/env python

import asyncio

from websockets.server import serve


async def print_message(websocket):
    async for message in websocket:
        print(message)


async def main():
    async with serve(print_message, "localhost", 8000):
        await asyncio.Future()  # run forever


try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("closing")
