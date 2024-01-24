import asyncio
from websockets import serve
from ypy_websocket import WebsocketServer

def callback():
    print("Message received!")

async def server():
    async with (
        WebsocketServer() as websocket_server,
        serve(websocket_server.serve, "localhost", 1234),
    ):
        room = await websocket_server.get_room('my-roomname')
        room.on_message = callback
        print(room.ready)
       
        await asyncio.Future()  # run forever

asyncio.run(server())
