import anyio
import websockets
from functools import partial
import sys
import logging

import click
from elva.click_utils import lazy_group
import ssl

SOCKETS = set()
log_handler = logging.StreamHandler(sys.stdout)
log = logging.getLogger(__name__)
log.addHandler(log_handler)
log.setLevel(logging.DEBUG)

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

def serve(host, port):
    try:
        anyio.run(run, host, port)
    except KeyboardInterrupt:
        log.info("closing connections...")
        for socket in SOCKETS.copy():
            log.debug(f"closing connection {socket}")
            socket.close()
        log.info("server stopped")
    except Exception as e:
        click.echo(e)

@lazy_group()
@click.option("--host", "-h", "host", default="localhost", show_default=True)
@click.option("--port", "-p", "port", default="8000", type=int, show_default=True)
def cli(host, port):
    serve(host, port)

if __name__ == "__main__":
    cli()