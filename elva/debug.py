import websockets
import anyio

async def main():
    async with websockets.connect("ws://elva.testing/", extra_headers={"Connection": "Upgrade", "Upgrade": "websocket"}) as websocket:
        print("request header:")
        print(websocket.request_headers)       
        print("response header:")
        print(websocket.response_headers)       

anyio.run(main)
