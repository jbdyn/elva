import anyio
import websockets
from functools import partial


SOCKETS = set()

async def broadcast(receive_stream):
    async with receive_stream:
        async for item in receive_stream:
            message_socket, message = item
            for socket in SOCKETS.copy():
                if message_socket != socket:
                    await socket.send(message)

async def handler(websocket, send_stream):
    SOCKETS.add(websocket)
    print(websocket.path)
    try:
        async for message in websocket:
            await send_stream.send((websocket, message))
    finally:
        SOCKETS.remove(websocket)

async def main():
    send_stream, receive_stream = anyio.create_memory_object_stream[str]()
    async with send_stream:
        async with websockets.serve(partial(handler, send_stream=send_stream), 'localhost', 1234) as server:
            await broadcast(receive_stream)

anyio.run(main)
