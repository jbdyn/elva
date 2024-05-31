import anyio
import websockets
from functools import partial
import sys
import logging
from logging import Logger

import click
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

@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx: click.Context):
    """local websocket server"""

    log_handler = logging.StreamHandler(sys.stdout)
    log = logging.getLogger(__name__)
    log.addHandler(log_handler)
    log.setLevel(logging.DEBUG)

    host = ctx.obj['local_websocket_host']
    port = ctx.obj['local_websocket_port']

    serve(host, port, log)

if __name__ == "__main__":
    cli()