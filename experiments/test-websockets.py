import base64

import anyio
import websockets


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
    async for ws in websockets.connect("ws://johndoe:janedoe@localhost:8000"):
        try:
            await loop(ws)
        except Exception as e:
            print(e)
            print(ws)


anyio.run(main)
