import asyncio
from websockets import serve
from pycrdt_websocket import WebsocketServer

def callback(event):
    print("server observed doc changes")
    print(event)
    return False

async def server():
    async with (
        WebsocketServer() as websocket_server,
        serve(websocket_server.serve, "localhost", 1234),
    ):
        room = await websocket_server.get_room("/my-roomname")
        print(type(room))
        print(f"Room is ready: {room.ready}")
        room.on_message = callback
        await asyncio.Future()  # run forever

asyncio.run(server())
