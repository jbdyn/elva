#!/usr/bin/env python

import asyncio
import base64

from websockets.server import serve


async def process_request(path, request_headers):
    print("processing request headers")
    print(request_headers)
    auth_method, credentials = request_headers["Authorization"].split(" ", maxsplit=1)
    print("CREDENTIALS", credentials)
    user, password = (
        base64.b64decode(credentials.encode()).decode().split(":", maxsplit=1)
    )
    print(user, password)


async def print_message(websocket):
    print(websocket, " connected!")
    async for message in websocket:
        print(message)


async def main():
    async with serve(print_message, "localhost", 8000, process_request=process_request):
        print("serving...")
        await asyncio.Future()  # run forever


try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("closing")
