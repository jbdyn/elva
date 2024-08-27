import base64

import anyio
import websockets
from websockets.exceptions import InvalidStatusCode


async def loop(ws):
    while True:
        await ws.send("test")
        await anyio.sleep(0.5)


async def main():
    user = "johndo"
    password = "janedoe"
    value = "{}:{}".format(user, password).encode()
    b64value = base64.b64encode(value).decode()
    assert type(b64value) is str
    headers = dict(Authorization="Basic " + b64value)
    print(headers)
    uri = "ws://{user}:{password}@localhost:8000"
    while True:
        exceptions = (InvalidStatusCode,)
        try:
            async with websockets.connect(
                uri.format(user=user, password=password)
            ) as ws:
                await loop(ws)
        except exceptions as exc:
            print(exc)
            print("exiting")
            break


try:
    anyio.run(main)
except KeyboardInterrupt:
    print("exiting")
    exit()
