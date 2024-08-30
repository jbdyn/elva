import base64

import anyio
import websockets
from websockets.exceptions import InvalidStatusCode, InvalidURI


async def loop(ws):
    while True:
        await ws.send("test")
        await anyio.sleep(0.5)


async def main():
    user = "johndoe"
    password = "janedoe"
    value = "{}:{}".format(user, password).encode()
    b64value = base64.b64encode(value).decode()
    assert type(b64value) is str
    headers = dict(Authorization="Basic " + b64value)
    print(headers)
    # uri = "ws://{user}:{password}@localhost:8000"
    uri = "ws://localhost:8000"

    while True:
        exceptions = (InvalidStatusCode, InvalidURI)
        try:
            async with websockets.connect(uri, extra_headers=headers) as ws:
                await loop(ws)
        except exceptions as exc:
            print(type(exc), exc)
            try:
                print(exc.headers)
            except:
                pass
            print("exiting")
            break


try:
    anyio.run(main)
except KeyboardInterrupt:
    print("exiting")
    exit()
