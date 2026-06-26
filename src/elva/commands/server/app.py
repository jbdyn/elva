"""
App definition.
"""

from anyio import create_task_group
from websockets.asyncio.server import basic_auth

from elva.auth import DummyAuth
from elva.config import Config
from elva.server import WebsocketServer, free_tcp_port


async def main(config: Config):
    """
    Main app routine.

    Starts a server component and handles process signals.

    Arguments:
        config: configuration parameter mapping.
    """
    c = config

    host = c.get("server.host", "0.0.0.0")
    port = c.get("server.port") or free_tcp_port()
    save = c.get("server.save", False)
    directory = c.get("server.directory")
    dummy = c.get("server.dummy", False)

    if dummy:
        process_request = DummyAuth().check
    else:
        process_request = None

    if process_request is not None:
        process_request = basic_auth(
            realm="ELVA WebSocket Server",
            check_credentials=process_request,
        )

    server = WebsocketServer(
        host=host,
        port=port,
        persistent=save,
        path=directory,
        process_request=process_request,
        tls_config=c.get("tls", {}),
    )

    async with create_task_group() as tg:
        await tg.start(server.start)
