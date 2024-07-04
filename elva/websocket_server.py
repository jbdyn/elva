import logging
import sys
from functools import partial
from logging import Logger

import anyio
import click
import websockets

from elva.click_utils import elva_app_cli

SOCKETS = set()

async def broadcast(receive_stream, log: Logger):
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

async def handler(websocket, send_stream, log: Logger):
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


async def run(host, port, log: Logger):
    send_stream, receive_stream = anyio.create_memory_object_stream()
    async with send_stream:
        async with websockets.serve(partial(handler, send_stream=send_stream, log=log), host, port) as server:
            log.info(f"start broadcasting on {host}:{port}")
            await broadcast(receive_stream, log)

def serve(host, port, log: Logger|None = None):
    log =  log or logging.getLogger(__name__)
    try:
        anyio.run(run, host, port, log)
    except KeyboardInterrupt:
        log.info("closing connections...")
        for socket in SOCKETS.copy():
            log.debug(f"closing connection {socket}")
            socket.close()
        log.info("server stopped")
    except Exception as e:
        click.echo(e)


@click.command
@click.pass_context
@click.argument(
    "host",
    default="localhost",
)
@click.argument(
    "port",
    default=8000,
)
def cli(ctx: click.Context, host: str, port: str):
    """local websocket server"""

    log_handler = logging.StreamHandler(sys.stdout)
    log = logging.getLogger(__name__)
    log.addHandler(log_handler)
    log.setLevel(logging.DEBUG)

    serve(host, port, log)

if __name__ == "__main__":
    cli()
