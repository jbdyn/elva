import websockets
import anyio

async def loop(ws):
    while True:
        await ws.send("test")
        await anyio.sleep(0.5)

async def main():
    async for ws in websockets.connect("ws://localhost:8000"):
        try:
            await anyio.sleep_forever()
        except Exception as e:
            print(e)
            print(ws)

anyio.run(main)
