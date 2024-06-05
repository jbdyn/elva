import anyio
import websockets
from functools import partial
import sys
import logging

import click
import ssl

SOCKETS = set()
log_handler = logging.StreamHandler(sys.stdout)
log = logging.getLogger(__name__)
log.addHandler(log_handler)
log.setLevel(logging.DEBUG)

async def authenticate(websocket):
    websocket.send("Please authenticate:")
    reply = await websocket.recv()
    # authenticator, LDAP
    # return authenticator.result()

async def broadcast(receive_stream):
    async with receive_stream:
        async for item in receive_stream:
            message_socket, message = item
            for socket in SOCKETS.copy():
                if socket != message_socket:
                    log.debug(f"> sending {message} to {socket}")
                    try:
                        await socket.send(message)
                    except Exception as e:
                        log.error(e)

async def handler(websocket, send_stream):
    auth_successful = await authenticate(websocket)
    if not auth_successful:
        await websocket.send("Invalid credentials. Closing connection.")
        await websocket.close()
        return

    SOCKETS.add(websocket)
    log.debug(f"added {websocket}")
    log.debug(f"all clients: {SOCKETS}")
    try:
        async for message in websocket:
            await send_stream.send((websocket, message))
    except Exception as e:
        log.error(e)
    finally:
        SOCKETS.remove(websocket)
        await websocket.close()
        log.debug(f"closed connection {websocket}")
        log.debug(f"all clients: {SOCKETS}")


async def run(host, port, **kwargs):
    send_stream, receive_stream = anyio.create_memory_object_stream()
    async with send_stream:
        async with websockets.serve(partial(handler, send_stream=send_stream), host, port) as server:
            log.info(f"start broadcasting on {host}:{port}")
            await broadcast(receive_stream)

if __name__ == "__main__":
    try:
        host = sys.argv[1]
        port = sys.argv[2]
    except Exception as e:
        log.error(e)
        log.info("using defaults")
        host = 'localhost'
        port = 8000
    try:
        anyio.run(run, host, port)
    except KeyboardInterrupt:
        log.info("closing connections...")
        for socket in SOCKETS.copy():
            log.debug(f"closing connection {socket}")
            sockets.close()
        log.info("server stopped")
